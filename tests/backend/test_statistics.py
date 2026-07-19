from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import Course, LearningRecord, PracticeAttempt, PracticeQuestion, StudyPlan, StudyPlanVersion, StudyTask, User


END = date(2026, 7, 19)


def _course(client: TestClient, headers: dict, name: str) -> int:
    response = client.post('/api/v1/courses', headers=headers, json={'name': name})
    assert response.status_code == 201
    return response.json()['data']['id']


def _other(client: TestClient) -> dict:
    credentials = {'email': 'statistics-other@example.com', 'password': 'statistics-password', 'display_name': 'Statistics Other'}
    assert client.post('/api/v1/auth/register', json=credentials).status_code == 201
    token = client.post('/api/v1/auth/login', json={'email': credentials['email'], 'password': credentials['password']}).json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}


def _user_id(client: TestClient) -> int:
    with client.app.state.database.session_factory() as db:
        user = db.scalar(select(User).where(User.email == 'learner@example.com'))
        user.timezone = 'Asia/Shanghai'
        db.commit()
        return user.id


def _record(client: TestClient, user_id: int, course_id: int, day: int, seconds: int, *, completed: bool = True):
    with client.app.state.database.session_factory() as db:
        db.add(LearningRecord(user_id=user_id, course_id=course_id, duration_seconds=seconds, completed=completed, occurred_at=datetime(2026, 7, day, 12, tzinfo=timezone.utc)))
        db.commit()


def _question(client: TestClient, course_id: int, seed: str) -> int:
    with client.app.state.database.session_factory() as db:
        question = PracticeQuestion(course_id=course_id, seed_key=seed, stem='统计练习题', options=[{'key': 'A', 'text': '正确'}, {'key': 'B', 'text': '错误'}], correct_option='A', explanation='解析')
        db.add(question); db.commit(); db.refresh(question)
        return question.id


def _attempt(client: TestClient, user_id: int, course_id: int, question_id: int, suffix: str, hour: int, correct: bool):
    with client.app.state.database.session_factory() as db:
        db.add(PracticeAttempt(submission_id=f'stat-{suffix}', user_id=user_id, course_id=course_id, question_id=question_id, selected_option='A' if correct else 'B', is_correct=correct, elapsed_seconds=20, submitted_at=datetime(2026, 7, 19, hour, tzinfo=timezone.utc)))
        db.commit()


def test_statistics_empty_state_and_full_date_axes(client: TestClient, auth_headers: dict):
    response = client.get('/api/v1/statistics/overview?days=7&end_date=2026-07-19', headers=auth_headers)
    data = response.json()['data']
    assert response.status_code == 200
    assert data['summary']['total_learning_seconds'] == 0
    assert data['summary']['task_completion_rate'] is None
    assert data['summary']['practice_accuracy'] is None
    assert data['summary']['efficient_period'] is None
    assert data['course_distribution'] == []
    assert len(data['daily']) == 7 and len(data['heatmap']) == 49
    assert data['insights'] == []


def test_statistics_learning_records_course_filter_timezone_and_distribution(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_a = _course(client, auth_headers, 'Course A'); course_b = _course(client, auth_headers, 'Course B')
    _record(client, user_id, course_a, 19, 3600); _record(client, user_id, course_a, 18, 1800); _record(client, user_id, course_b, 19, 600); _record(client, user_id, course_a, 19, 999, completed=False)
    all_data = client.get('/api/v1/statistics/overview?days=7&end_date=2026-07-19', headers=auth_headers).json()['data']
    scoped = client.get(f'/api/v1/statistics/overview?days=7&course_id={course_a}&end_date=2026-07-19', headers=auth_headers).json()['data']
    assert all_data['summary']['total_learning_seconds'] == 6000
    assert scoped['summary']['total_learning_seconds'] == 5400
    assert [item['course_name'] for item in all_data['course_distribution']] == ['Course A', 'Course B']
    assert all_data['daily'][-1]['actual_learning_seconds'] == 4200
    assert scoped['summary']['learning_days'] == 2


def test_statistics_active_tasks_and_previous_period_rate(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_id = _course(client, auth_headers, 'Planned course')
    with client.app.state.database.session_factory() as db:
        plan = StudyPlan(user_id=user_id, course_id=course_id, goal='goal', start_date=date(2026, 7, 1), end_date=date(2026, 7, 31), active_version=1, status='active')
        db.add(plan); db.flush(); active = StudyPlanVersion(plan_id=plan.id, version=1, status='active'); candidate = StudyPlanVersion(plan_id=plan.id, version=2, status='candidate'); db.add_all([active, candidate]); db.flush()
        db.add_all([StudyTask(plan_version_id=active.id, user_id=user_id, course_id=course_id, scheduled_date=END, title='done', task_type='review', estimated_minutes=30, status='completed'), StudyTask(plan_version_id=active.id, user_id=user_id, course_id=course_id, scheduled_date=END, title='todo', task_type='review', estimated_minutes=40, status='todo'), StudyTask(plan_version_id=candidate.id, user_id=user_id, course_id=course_id, scheduled_date=END, title='hidden', task_type='review', estimated_minutes=99, status='completed')])
        db.commit()
    data = client.get(f'/api/v1/statistics/overview?days=7&course_id={course_id}&end_date=2026-07-19', headers=auth_headers).json()['data']
    assert data['summary']['task_total'] == 2 and data['summary']['task_completed'] == 1
    assert data['daily'][-1]['planned_minutes'] == 70
    assert data['summary']['task_completion_rate'] == 0.5
    assert data['summary']['previous_task_completion_rate'] is None


def test_statistics_practice_efficient_period_and_user_isolation(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_id = _course(client, auth_headers, 'Practice course'); question_id = _question(client, course_id, 'statistics-practice')
    for index, correct in enumerate((True, True, False)):
        _attempt(client, user_id, course_id, question_id, str(index), 12, correct)
    other_headers = _other(client); other_course = _course(client, other_headers, 'Other course'); other_question = _question(client, other_course, 'statistics-other');
    with client.app.state.database.session_factory() as db:
        other_user = db.scalar(select(User).where(User.email == 'statistics-other@example.com'))
    _attempt(client, other_user.id, other_course, other_question, 'other', 12, True)
    data = client.get(f'/api/v1/statistics/overview?days=7&course_id={course_id}&end_date=2026-07-19', headers=auth_headers).json()['data']
    assert data['summary']['practice_attempts'] == 3 and data['summary']['practice_accuracy'] == 0.6667
    assert data['summary']['efficient_period']['label'] == '20:00–22:00'
    assert client.get(f'/api/v1/statistics/overview?course_id={course_id}', headers=other_headers).status_code == 404


def test_statistics_csv_is_read_only_safe_and_matches_daily(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_id = _course(client, auth_headers, '=Formula course'); _record(client, user_id, course_id, 19, 1800)
    with client.app.state.database.session_factory() as db:
        before = db.scalar(select(func.count()).select_from(LearningRecord))
    response = client.get(f'/api/v1/statistics/export.csv?days=7&course_id={course_id}&end_date=2026-07-19', headers=auth_headers)
    with client.app.state.database.session_factory() as db:
        after = db.scalar(select(func.count()).select_from(LearningRecord))
    assert response.status_code == 200 and response.headers['content-type'].startswith('text/csv')
    assert 'study-statistics-2026-07-13-to-2026-07-19.csv' in response.headers['content-disposition']
    assert response.content.startswith(b'\xef\xbb\xbf')
    assert response.text.count('\n') == 8
    assert "'=Formula course" in response.text
    assert before == after


def test_statistics_query_validation_archived_course_and_get_read_only(client: TestClient, auth_headers: dict):
    course_id = _course(client, auth_headers, 'Archived statistics course')
    assert client.get('/api/v1/statistics/overview').status_code == 401
    assert client.get('/api/v1/statistics/overview?days=0', headers=auth_headers).status_code == 422
    assert client.get('/api/v1/statistics/overview?days=91', headers=auth_headers).status_code == 422
    with client.app.state.database.session_factory() as db:
        course = db.get(Course, course_id); course.archived = True; db.commit()
        before = (db.scalar(select(func.count()).select_from(LearningRecord)), db.scalar(select(func.count()).select_from(PracticeAttempt)), db.scalar(select(func.count()).select_from(StudyTask)))
    assert client.get(f'/api/v1/statistics/overview?course_id={course_id}', headers=auth_headers).status_code == 404
    assert client.get('/api/v1/statistics/overview?days=7&end_date=2026-07-19', headers=auth_headers).status_code == 200
    with client.app.state.database.session_factory() as db:
        after = (db.scalar(select(func.count()).select_from(LearningRecord)), db.scalar(select(func.count()).select_from(PracticeAttempt)), db.scalar(select(func.count()).select_from(StudyTask)))
    assert before == after
