import uuid
import json
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)
CORS(app)

# DynamoDB setup — uses IAM Role attached to EC2 (no hardcoded keys)
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
assignments_table  = dynamodb.Table('ASSIGNMENTS')
submissions_table  = dynamodb.Table('SUBMISSIONS')


# ────────────────────────────────────────────
#  HEALTH CHECK
# ────────────────────────────────────────────
@app.route('/', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Assignment Tracker API is running"})


# ────────────────────────────────────────────
#  ASSIGNMENTS
# ────────────────────────────────────────────

@app.route('/assignments', methods=['GET'])
def get_assignments():
    try:
        response = assignments_table.scan()
        items = response.get('Items', [])
        # Sort by due_date ascending
        items.sort(key=lambda x: x.get('due_date', ''))
        return jsonify(items), 200
    except ClientError as e:
        return jsonify({"error": str(e)}), 500


@app.route('/assignments', methods=['POST'])
def create_assignment():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required = ['title', 'subject', 'due_date', 'max_marks']
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    item = {
        'assignment_id': str(uuid.uuid4()),
        'title':         data['title'],
        'subject':       data['subject'],
        'due_date':      data['due_date'],
        'max_marks':     int(data['max_marks']),
        'description':   data.get('description', ''),
        'created_at':    datetime.utcnow().isoformat()
    }

    try:
        assignments_table.put_item(Item=item)
        return jsonify(item), 201
    except ClientError as e:
        return jsonify({"error": str(e)}), 500


@app.route('/assignments/<assignment_id>', methods=['GET'])
def get_assignment(assignment_id):
    try:
        response = assignments_table.get_item(Key={'assignment_id': assignment_id})
        item = response.get('Item')
        if not item:
            return jsonify({"error": "Assignment not found"}), 404
        return jsonify(item), 200
    except ClientError as e:
        return jsonify({"error": str(e)}), 500


@app.route('/assignments/<assignment_id>', methods=['DELETE'])
def delete_assignment(assignment_id):
    try:
        # Check exists
        response = assignments_table.get_item(Key={'assignment_id': assignment_id})
        if not response.get('Item'):
            return jsonify({"error": "Assignment not found"}), 404

        assignments_table.delete_item(Key={'assignment_id': assignment_id})
        return jsonify({"message": "Assignment deleted successfully"}), 200
    except ClientError as e:
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────
#  SUBMISSIONS
# ────────────────────────────────────────────

@app.route('/submissions', methods=['GET'])
def get_submissions():
    try:
        response = submissions_table.scan()
        items = response.get('Items', [])
        items.sort(key=lambda x: x.get('submitted_at', ''), reverse=True)
        return jsonify(items), 200
    except ClientError as e:
        return jsonify({"error": str(e)}), 500


@app.route('/submissions', methods=['POST'])
def create_submission():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required = ['student_name', 'student_id', 'assignment_id']
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    # Verify assignment exists
    try:
        asgn_resp = assignments_table.get_item(Key={'assignment_id': data['assignment_id']})
        if not asgn_resp.get('Item'):
            return jsonify({"error": "Assignment not found"}), 404
    except ClientError as e:
        return jsonify({"error": str(e)}), 500

    item = {
        'submission_id': str(uuid.uuid4()),
        'student_name':  data['student_name'],
        'student_id':    data['student_id'],
        'assignment_id': data['assignment_id'],
        'notes':         data.get('notes', ''),
        'submitted_at':  data.get('submitted_at', datetime.utcnow().isoformat()),
        'status':        'submitted',
        'marks_awarded': None,
        'feedback':      ''
    }

    try:
        submissions_table.put_item(Item=item)
        return jsonify(item), 201
    except ClientError as e:
        return jsonify({"error": str(e)}), 500


@app.route('/submissions/<submission_id>', methods=['GET'])
def get_submission(submission_id):
    try:
        response = submissions_table.get_item(Key={'submission_id': submission_id})
        item = response.get('Item')
        if not item:
            return jsonify({"error": "Submission not found"}), 404
        return jsonify(item), 200
    except ClientError as e:
        return jsonify({"error": str(e)}), 500


@app.route('/submissions/<submission_id>/grade', methods=['PUT'])
def grade_submission(submission_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    if 'marks_awarded' not in data:
        return jsonify({"error": "marks_awarded is required"}), 400

    try:
        response = submissions_table.get_item(Key={'submission_id': submission_id})
        if not response.get('Item'):
            return jsonify({"error": "Submission not found"}), 404

        submissions_table.update_item(
            Key={'submission_id': submission_id},
            UpdateExpression="SET marks_awarded = :m, feedback = :f, #s = :s, graded_at = :g",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':m': int(data['marks_awarded']),
                ':f': data.get('feedback', ''),
                ':s': 'graded',
                ':g': datetime.utcnow().isoformat()
            }
        )
        return jsonify({"message": "Submission graded successfully"}), 200
    except ClientError as e:
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────
#  RUN
# ────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
