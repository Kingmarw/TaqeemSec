from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
app = Flask(__name__)  # تأكد إنك معرف التطبيق
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/user.db'  # أو أي مسار لقاعدة البيانات
db = SQLAlchemy(app)
migrate = Migrate(app, db)  # 🔥 ده اللي كان ناقص!
