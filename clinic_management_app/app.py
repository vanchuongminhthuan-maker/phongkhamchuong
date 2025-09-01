from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, UTC

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clinic.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ==========================
# Models
# ==========================
class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dob = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

class Medicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    form = db.Column(db.String(50))  # dạng thuốc (viên, gói, lọ...)
    quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Float, default=0.0)
    total_cost = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

# ✅ TẠO BẢNG NGAY KHI KHỞI ĐỘNG (an toàn trên Render + Gunicorn)
with app.app_context():
    db.create_all()

# (Tuỳ chọn) vẫn có thể giữ, nhưng không còn bắt buộc
# @app.before_first_request
# def init_db():
#     db.create_all()

# ==========================
# Routes
# ==========================
@app.route('/')
def index():
    today = datetime.now(UTC).date()
    patients = Patient.query.filter(db.func.date(Patient.created_at) == today).all()
    return render_template('index.html', patients=patients)

@app.route('/add_patient', methods=['POST'])
def add_patient():
    name = request.form['name']
    dob = request.form.get('dob')
    phone = request.form.get('phone')
    patient = Patient(name=name, dob=dob, phone=phone)
    db.session.add(patient)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/add_medicine', methods=['POST'])
def add_medicine():
    name = request.form['name']
    form = request.form.get('form')
    quantity = int(request.form['quantity'])
    price = float(request.form['price'])
    total_cost = float(request.form['total_cost'])
    medicine = Medicine(name=name, form=form, quantity=quantity, price=price, total_cost=total_cost)
    db.session.add(medicine)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/search_patient', methods=['GET'])
def search_patient():
    keyword = request.args.get('q', '')
    results = Patient.query.filter(Patient.name.like(f"%{keyword}%")).all()
    return jsonify([{'id': p.id, 'name': p.name, 'dob': p.dob, 'phone': p.phone} for p in results])

# (chỉ dùng khi chạy local bằng `python app.py`)
if __name__ == '__main__':
    app.run()
