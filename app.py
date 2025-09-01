from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, UTC, timedelta
from sqlalchemy import CheckConstraint

app = Flask(__name__)
app.secret_key = "secret"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clinic.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

def calc_age(dob_str: str):
    if not dob_str:
        return "-"
    try:
        d, m, y = [int(x) for x in dob_str.split("/")]
        b = date(y, m, d)
        today = datetime.now(UTC).date()
        return today.year - b.year - ((today.month, today.day) < (b.month, b.day))
    except Exception:
        return "?"

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    dob = db.Column(db.String(20))
    gender = db.Column(db.String(10), default="")
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    arrival_time = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    status = db.Column(db.String(20), default="chờ khám")
    patient = db.relationship('Patient', backref=db.backref('visits', lazy=True))

class Medicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    form = db.Column(db.String(50))
    unit = db.Column(db.String(20), default="viên")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

class InventoryLot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicine.id'), nullable=False)
    lot_no = db.Column(db.String(60))
    received_date = db.Column(db.DateTime)
    expiry_date = db.Column(db.DateTime)
    qty_in = db.Column(db.Integer, default=0)
    qty_remaining = db.Column(db.Integer, default=0)
    unit_cost = db.Column(db.Float, default=0.0)
    medicine = db.relationship('Medicine', backref=db.backref('lots', lazy=True))
    __table_args__ = (CheckConstraint('qty_in >= 0'), CheckConstraint('qty_remaining >= 0'),)

class Dispense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey('visit.id'), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicine.id'), nullable=False)
    lot_id = db.Column(db.Integer, db.ForeignKey('inventory_lot.id'), nullable=True)
    qty = db.Column(db.Integer, default=0)
    unit_cost = db.Column(db.Float, default=0.0)
    unit_price = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    visit = db.relationship('Visit', backref=db.backref('dispenses', lazy=True))
    medicine = db.relationship('Medicine')
    lot = db.relationship('InventoryLot')

with app.app_context():
    db.create_all()

def fifo_dispense(visit_id: int, medicine_id: int, qty: int, unit_price: float):
    if qty <= 0:
        raise ValueError("Số lượng phải > 0")
    lots = (InventoryLot.query
            .filter_by(medicine_id=medicine_id)
            .filter(InventoryLot.qty_remaining > 0)
            .order_by(InventoryLot.received_date.asc(), InventoryLot.id.asc())
            .all())
    remain = qty
    total_cost = 0.0
    total_revenue = 0.0
    for lot in lots:
        if remain == 0:
            break
        take = min(lot.qty_remaining, remain)
        lot.qty_remaining -= take
        cost = take * (lot.unit_cost or 0.0)
        revenue = take * unit_price
        d = Dispense(
            visit_id=visit_id,
            medicine_id=medicine_id,
            lot_id=lot.id,
            qty=take,
            unit_cost=lot.unit_cost or 0.0,
            unit_price=unit_price
        )
        db.session.add(d)
        total_cost += cost
        total_revenue += revenue
        remain -= take
    if remain > 0:
        raise ValueError("Tồn kho không đủ")
    db.session.commit()
    return total_cost, total_revenue, total_revenue - total_cost

@app.route("/")
def home():
    today = datetime.now(UTC).date()
    visits = (Visit.query
              .join(Patient, Visit.patient_id == Patient.id)
              .filter(db.func.date(Visit.arrival_time) == today)
              .order_by(Visit.arrival_time.asc())
              .all())
    return render_template("index.html", visits=visits, calc_age=calc_age)

@app.route("/patients")
def patients_page():
    q = request.args.get("q", "").strip()
    query = Patient.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Patient.name.like(like), Patient.phone.like(like)))
    patients = query.order_by(Patient.created_at.desc()).limit(100).all()
    return render_template("patients.html", patients=patients, q=q, calc_age=calc_age)

@app.route("/patients/new_visit", methods=["POST"])
def new_visit():
    patient_id = int(request.form["patient_id"])
    v = Visit(patient_id=patient_id, status="chờ khám")
    db.session.add(v)
    db.session.commit()
    flash("Đã tạo lần khám mới", "success")
    return redirect(url_for("home"))

@app.route("/patients/add", methods=["POST"])
def add_patient():
    name = request.form["name"]
    dob = request.form.get("dob")
    gender = request.form.get("gender", "")
    phone = request.form.get("phone")
    p = Patient(name=name, dob=dob, gender=gender, phone=phone)
    db.session.add(p)
    db.session.commit()
    flash("Đã thêm bệnh nhân", "success")
    return redirect(url_for("patients_page"))

@app.route("/inventory")
def inventory_page():
    meds = Medicine.query.order_by(Medicine.name.asc()).all()
    lots = (db.session.query(InventoryLot, Medicine.name.label("med_name"), Medicine.form.label("med_form"), Medicine.unit.label("med_unit"))
            .join(Medicine, InventoryLot.medicine_id == Medicine.id)
            .order_by(InventoryLot.expiry_date.asc().nullsLast(), InventoryLot.id.desc())
            .all())
    return render_template("inventory.html", meds=meds, lots=lots)

@app.route("/inventory/add_medicine", methods=["POST"])
def add_medicine():
    name = request.form["name"]
    form_ = request.form.get("form")
    unit = request.form.get("unit")
    m = Medicine(name=name, form=form_, unit=unit or "viên")
    db.session.add(m)
    db.session.commit()
    flash("Đã thêm thuốc", "success")
    return redirect(url_for("inventory_page"))

@app.route("/inventory/add_lot", methods=["POST"])
def add_lot():
    med_id = int(request.form["medicine_id"])
    lot_no = request.form.get("lot_no")
    received_date = request.form.get("received_date")
    expiry_date = request.form.get("expiry_date")
    qty_in = int(request.form["qty_in"])
    price_mode = request.form.get("price_mode", "unit")
    price_input = float(request.form.get("price", 0))
    unit_cost = (price_input / qty_in) if (price_mode == "total" and qty_in > 0) else price_input
    lot = InventoryLot(
        medicine_id=med_id,
        lot_no=lot_no,
        received_date=datetime.fromisoformat(received_date) if received_date else None,
        expiry_date=datetime.fromisoformat(expiry_date) if expiry_date else None,
        qty_in=qty_in,
        qty_remaining=qty_in,
        unit_cost=unit_cost,
    )
    db.session.add(lot)
    db.session.commit()
    flash("Đã nhập kho lô thuốc", "success")
    return redirect(url_for("inventory_page"))

@app.route("/dispense", methods=["POST"])
def dispense_route():
    visit_id = int(request.form["visit_id"])
    medicine_id = int(request.form["medicine_id"])
    qty = int(request.form["qty"])
    unit_price = float(request.form["unit_price"])
    try:
        cost, revenue, profit = fifo_dispense(visit_id, medicine_id, qty, unit_price)
        flash(f"Xuất kho thành công. Giá vốn: {cost:.2f} | Doanh thu: {revenue:.2f} | Lợi nhuận: {profit:.2f}", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("home"))

@app.route("/reports")
def reports_page():
    s_from = request.args.get("from")
    s_to = request.args.get("to")
    q = Dispense.query
    if s_from:
        q = q.filter(Dispense.created_at >= datetime.fromisoformat(s_from))
    if s_to:
        q = q.filter(Dispense.created_at <= datetime.fromisoformat(s_to) + timedelta(days=1))
    rows = q.order_by(Dispense.created_at.desc()).limit(500).all()
    total_cost = sum((d.qty or 0) * (d.unit_cost or 0) for d in rows)
    total_rev = sum((d.qty or 0) * (d.unit_price or 0) for d in rows)
    total_profit = total_rev - total_cost
    return render_template("reports.html", rows=rows, total_cost=total_cost, total_rev=total_rev, total_profit=total_profit)

@app.route("/settings")
def settings_page():
    return render_template("settings.html")

if __name__ == "__main__":
    app.run()
