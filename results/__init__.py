import logging.handlers
import MySQLdb
from flask import Flask, render_template, g
import index

app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('imp-results.cfg')

if not app.debug and 'MAIL_SERVER' in app.config:
    mail_handler = logging.handlers.SMTPHandler(
        mailhost=(app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
        fromaddr='no-reply@' + app.config['MAIL_SERVER'],
        toaddrs=app.config['ADMINS'], subject='IMP nightly build page error')
    mail_handler.setLevel(logging.ERROR)
    app.logger.addHandler(mail_handler)


def _connect_db():
    conn = MySQLdb.connect(host=app.config['HOST'], user=app.config['USER'],
                           passwd=app.config['PASSWORD'],
                           db=app.config['DATABASE'])
    return conn


def get_db():
    """Open a new database connection if necessary"""
    if not hasattr(g, 'db_conn'):
        g.db_conn = _connect_db()
    return g.db_conn


@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'db_conn'):
        g.db_conn.close()


@app.route('/')
def summary():
    return render_template('layout.html')


@app.route('/platform/<int:platform_id>')
def platform(platform_id):
    p = index.TestPage(get_db(), app.config)
    return p.display_platform(platform_id)


@app.route('/component/<int:component_id>')
def component(component_id):
    p = index.TestPage(get_db(), app.config)
    return p.display_component(component_id)
