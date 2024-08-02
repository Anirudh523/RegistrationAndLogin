from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_mysqldb import MySQL
import MySQLdb.cursors
import re
import time
import logging
from winotify import Notification, audio

app = Flask(__name__)

app.secret_key = 'your secret key'

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Doddhuduga1$'
app.config['MYSQL_DB'] = 'anislogin'

mysql = MySQL(app)
scheduler = BackgroundScheduler()
scheduler.start()
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')


class Task:
    def __init__(self, description, start_time, duration, user_id=None, id=None):
        self.description = description
        self.start_time = start_time
        self.end_time = start_time + timedelta(minutes=duration)
        self.duration = duration
        self.id = id
        self.user_id = user_id

    def save_to_db(self, cursor):
        if self.id is None:
            # Insert a new task
            cursor.execute(
                'INSERT INTO tasks (user_id, description, start_time, duration) VALUES (%s, %s, %s, %s)',
                (self.user_id, self.description, self.start_time, self.duration))
        else:
            # Update existing task
            cursor.execute('UPDATE tasks SET description = %s, start_time = %s, duration = %s WHERE id = %s',
                           (self.description, self.start_time, self.duration, self.id))

    @staticmethod
    def get_all_tasks(cursor, user_id):
        cursor.execute('SELECT * FROM tasks WHERE user_id = %s', (user_id,))
        tasks_data = cursor.fetchall()
        return [Task(**task) for task in tasks_data]

    @staticmethod
    def get_task(cursor, task_id):
        cursor.execute('SELECT * FROM tasks WHERE id = %s', (task_id,))
        task_data = cursor.fetchone()
        return Task(**task_data) if task_data else None

    def delete(self, cursor):
        if self.id:
            cursor.execute('DELETE FROM tasks WHERE id = %s', (self.id,))


@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM accounts WHERE username = % s AND password = % s', (username, password,))
        account = cursor.fetchone()
        if account:
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            msg = 'Logged in successfully !'
            return render_template('tasks.html', msg=msg)
        else:
            msg = 'Incorrect username / password !'
    return render_template('login.html', msg=msg)


@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    return redirect(url_for('login'))


@app.route('/tasks')
def tasks():
    if 'loggedin' in session:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM tasks WHERE user_id = %s', (session['id'],))
        tasks = cursor.fetchall()
        return render_template('tasks.html', tasks=tasks)
    return redirect(url_for('login'))


@app.route('/tasks/get')
def get_tasks():
    if 'loggedin' in session:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        now = datetime.now()
        cursor.execute("SELECT * FROM tasks WHERE user_id = %s", (session['id'],))
        tasks = cursor.fetchall()
        cursor.close()
        return jsonify({"tasks": tasks})  # Ensure this is the correct format
    return jsonify({"tasks": []})  # Return empty tasks if not logged in


@app.route('/tasks/create', methods=['GET', 'POST'])
def create_task():
    if 'loggedin' in session:
        if request.method == 'POST':
            description = request.form['description']
            duration = int(request.form['duration'])
            start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
            task = Task(description=description, duration=duration, start_time=start_time, user_id=session['id'])
            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            task.save_to_db(cursor)
            mysql.connection.commit()
            return redirect(url_for('tasks'))
        return render_template('create_task.html')
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form and 'email' in request.form:
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM accounts WHERE username = % s', (username,))
        account = cursor.fetchone()
        if account:
            msg = 'Account already exists !'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            msg = 'Invalid email address !'
        elif not re.match(r'[A-Za-z0-9]+', username):
            msg = 'Username must contain only characters and numbers !'
        elif not username or not password or not email:
            msg = 'Please fill out the form !'
        else:
            cursor.execute('INSERT INTO accounts VALUES (NULL, % s, % s, % s)', (username, password, email,))
            mysql.connection.commit()
            msg = 'You have successfully registered !'
    elif request.method == 'POST':
        msg = 'Please fill out the form !'
    return render_template('register.html', msg=msg)


def check_tasks():
    with app.app_context():
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        now = datetime.now()
        # Check for tasks that are starting
        cursor.execute("SELECT * FROM tasks WHERE TIMESTAMPDIFF(MINUTE, NOW(), start_time) BETWEEN 0 AND 1")
        starting_tasks = cursor.fetchall()

        # Check for tasks that are ending
        cursor.execute(
            """SELECT * FROM tasks WHERE TIMESTAMPDIFF(MINUTE, NOW(), start_time + INTERVAL duration MINUTE) BETWEEN 
            0 AND 1""")
        ending_tasks = cursor.fetchall()

        cursor.close()

        # Notify for starting tasks
        for task in starting_tasks:
            notify_user(task['user_id'], task['description'], "start")

        # Notify for ending tasks
        for task in ending_tasks:
            notify_user(task['user_id'], task['description'], "end")


def notify_user(user_id, task_description, notification_type):
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT email FROM accounts WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        cursor.close()

        if user:
            title = "Task Notification"
            if (notification_type == "start"):
                msg = f"Your task '{task_description}' is starting now."
                icon = r"C:\Users\Anirudh\Documents\GitHub\RegistrationAndLogin\Starting.png"
            else:
                msg = f"Your task '{task_description}' is ending soon, please extend if you are not finished"
                icon = r"C:\Users\Anirudh\Documents\GitHub\RegistrationAndLogin\Ending.png"
            # Log that we are about to show a notification
            logging.info(f"Notifying user {user_id} about task: {task_description} {notification_type}")
            # Show Windows notification
            toast = Notification(
                app_id="Task Reminder",
                title="Task Notification",
                msg=msg,
                duration="short",
                icon=icon
            )
            toast.set_audio(audio.Reminder, loop=False)
            toast.show()
        else:
            logging.warning(f"No user found with ID {user_id}")
    except Exception as e:
        logging.error(f"Error notifying user: {e}")


@app.route('/tasks/get_notifications')
def get_notifications():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    now = datetime.now()
    cursor.execute("SELECT * FROM tasks WHERE TIMESTAMPDIFF(MINUTE, NOW(), start_time) BETWEEN 0 AND 1")
    tasks = cursor.fetchall()
    cursor.close()
    return jsonify(tasks=tasks)


scheduler.add_job(check_tasks, 'interval', minutes=1)


@app.route('/tasks/extend/<int:task_id>', methods=['POST'])
def extend_task(task_id):
    if 'loggedin' in session:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        # Fetch the task details
        cursor.execute('SELECT * FROM tasks WHERE id = %s AND user_id = %s', (task_id, session['id']))
        task = cursor.fetchone()

        if task:
            # Calculate time remaining
            end_time = task['start_time'] + timedelta(minutes=task['duration'])

            time_remaining = (end_time - datetime.now()).total_seconds() / 60  # in minutes
            print(f"Current time: {datetime.now()}")
            print(f"Task end time: {end_time}")
            print(f"Time remaining: {time_remaining} minutes")
            if time_remaining <= 10 and not task['completed']:
                # Extend the task by 10 minutes or any desired duration
                new_duration = task['duration'] + 10
                cursor.execute('UPDATE tasks SET duration = %s WHERE id = %s', (new_duration, task_id))
                mysql.connection.commit()
                return jsonify({"status": "success", "message": "Task duration extended."})
            else:
                return jsonify({"status": "fail", "message": "Task cannot be extended."})

        return jsonify({"status": "fail", "message": "Task not found or unauthorized."})

    return redirect(url_for('login'))


def schedule_task_deletion(task_id, delay_minutes):
    scheduler.add_job(delete_task, 'date', run_date=datetime.now() + timedelta(minutes=delay_minutes), args=[task_id])

def delete_task(task_id):
    with app.app_context():
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('DELETE FROM tasks WHERE id = %s', (task_id,))
        mysql.connection.commit()
        cursor.close()
        logging.info(f"Task with ID {task_id} deleted.")


if __name__ == '__main__':
    app.run(debug=True)
