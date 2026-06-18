from flask import Flask, jsonify, request, abort
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import time

app = Flask(__name__)

# ── Prometheus Metrics ──────────────────────────────────────────
request_count = Counter(
    'task_api_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status']
)

request_latency = Histogram(
    'task_api_request_duration_seconds',
    'Request latency in seconds',
    ['endpoint']
)

error_count = Counter(
    'task_api_errors_total',
    'Total number of errors',
    ['endpoint']
)

active_requests = Gauge(
    'task_api_active_requests',
    'Number of requests currently being processed'
)

task_count = Gauge(
    'task_api_task_count',
    'Total number of tasks in the system'
)

# ── In-memory task storage ───────────────────────────────────────
tasks = {}
next_id = 1

# ── Helper: track metrics on every request ───────────────────────
def track(endpoint, method, status, start):
    duration = time.time() - start
    request_count.labels(method=method, endpoint=endpoint, status=status).inc()
    request_latency.labels(endpoint=endpoint).observe(duration)

# ── Routes ───────────────────────────────────────────────────────
@app.route('/tasks', methods=['GET'])
def get_tasks():
    start = time.time()
    active_requests.inc()
    try:
        track('/tasks', 'GET', 200, start)
        return jsonify({"tasks": list(tasks.values()), "count": len(tasks)}), 200
    finally:
        active_requests.dec()

@app.route('/tasks/<int:task_id>', methods=['GET'])
def get_task(task_id):
    start = time.time()
    active_requests.inc()
    try:
        task = tasks.get(task_id)
        if not task:
            error_count.labels(endpoint='/tasks/<id>').inc()
            track('/tasks/<id>', 'GET', 404, start)
            return jsonify({"error": "Task not found"}), 404
        track('/tasks/<id>', 'GET', 200, start)
        return jsonify(task), 200
    finally:
        active_requests.dec()

@app.route('/tasks', methods=['POST'])
def create_task():
    global next_id
    start = time.time()
    active_requests.inc()
    try:
        data = request.get_json()
        if not data or 'title' not in data:
            error_count.labels(endpoint='/tasks').inc()
            track('/tasks', 'POST', 400, start)
            return jsonify({"error": "Title is required"}), 400
        task = {
            "id": next_id,
            "title": data['title'],
            "done": False
        }
        tasks[next_id] = task
        next_id += 1
        task_count.set(len(tasks))
        track('/tasks', 'POST', 201, start)
        return jsonify(task), 201
    finally:
        active_requests.dec()

@app.route('/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    start = time.time()
    active_requests.inc()
    try:
        if task_id not in tasks:
            error_count.labels(endpoint='/tasks/<id>').inc()
            track('/tasks/<id>', 'DELETE', 404, start)
            return jsonify({"error": "Task not found"}), 404
        del tasks[task_id]
        task_count.set(len(tasks))
        track('/tasks/<id>', 'DELETE', 200, start)
        return jsonify({"message": "Task deleted"}), 200
    finally:
        active_requests.dec()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "tasks_in_memory": len(tasks)}), 200

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

# ── Run ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)