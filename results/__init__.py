import logging.handlers
from flask import Flask, render_template


app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('imp-results.cfg')

if not app.debug and 'MAIL_SERVER' in app.config:
    mail_handler = logging.handlers.SMTPHandler(
        mailhost=(app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
        fromaddr='no-reply@' + app.config['MAIL_SERVER'],
        toaddrs=app.config['ADMINS'], subject='IMP nightly build page error')
    mail_handler.setLevel(logging.ERROR)
    app.logger.addHandler(mail_handler)


@app.route('/')
def summary():
    return render_template('layout.html')
