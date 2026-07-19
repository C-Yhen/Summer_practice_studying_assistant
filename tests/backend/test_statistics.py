import csv
import io
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


def _record_at(client: TestClient, user_id: int, course_id: int, when: datetime, seconds: int):
    with client.app.state.database.session_factory() as db:
        db.add(LearningRecord(user_id=user_id, course_id=course_id, duration_seconds=seconds, completed=True, occurred_at=when))
        db.commit()


def _attempt_at(client: TestClient, user_id: int, course_id: int, question_id: int, suffix: str, when: datetime, correct: bool):
    with client.app.state.database.session_factory() as db:
        db.add(PracticeAttempt(submission_id=f'stat-at-{suffix}', user_id=user_id, course_id=course_id, question_id=question_id, selected_option='A' if correct else 'B', is_correct=correct, elapsed_seconds=20, submitted_at=when))
        db.commit()


def _active_plan_tasks(client: TestClient, user_id: int, course_id: int, tasks: list[tuple[date, str]]):
    with client.app.state.database.session_factory() as db:
        plan = StudyPlan(user_id=user_id, course_id=course_id, goal='statistics', start_date=date(2026, 6, 1), end_date=date(2026, 7, 31), active_version=1, status='active')
        db.add(plan); db.flush()
        version = StudyPlanVersion(plan_id=plan.id, version=1, status='active')
        db.add(version); db.flush()
        db.add_all([StudyTask(plan_version_id=version.id, user_id=user_id, course_id=course_id, scheduled_date=scheduled_date, title=f'task-{index}', task_type='review', estimated_minutes=20, status=status) for index, (scheduled_date, status) in enumerate(tasks)])
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


def test_statistics_previous_period_comparisons_are_exact(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_id = _course(client, auth_headers, 'Comparison course'); question_id = _question(client, course_id, 'comparison')
    _record_at(client, user_id, course_id, datetime(2026, 7, 18, 12, tzinfo=timezone.utc), 3600)
    _record_at(client, user_id, course_id, datetime(2026, 7, 10, 12, tzinfo=timezone.utc), 1800)
    _active_plan_tasks(client, user_id, course_id, [(date(2026, 7, 18), 'completed'), (date(2026, 7, 18), 'todo'), (date(2026, 7, 10), 'completed'), (date(2026, 7, 10), 'completed')])
    for index, correct in enumerate((True, True, False)):
        _attempt_at(client, user_id, course_id, question_id, f'current-{index}', datetime(2026, 7, 18, 12, tzinfo=timezone.utc), correct)
    for index in range(3):
        _attempt_at(client, user_id, course_id, question_id, f'previous-{index}', datetime(2026, 7, 10, 12, tzinfo=timezone.utc), True)
    summary = client.get(f'/api/v1/statistics/overview?days=7&course_id={course_id}&end_date=2026-07-19', headers=auth_headers).json()['data']['summary']
    assert summary['previous_total_learning_seconds'] == 1800 and summary['learning_seconds_change'] == 1800
    assert summary['previous_task_completion_rate'] == 1 and summary['task_completion_rate_change'] == -0.5
    assert summary['previous_practice_accuracy'] == 1 and summary['practice_accuracy_change'] == -0.3333


def test_statistics_thirty_day_axis_heatmap_streak_and_course_scope(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_a = _course(client, auth_headers, 'Heat A'); course_b = _course(client, auth_headers, 'Heat B')
    for day in (17, 18, 19):
        _record_at(client, user_id, course_a, datetime(2026, 7, day, 12, tzinfo=timezone.utc), 600)
    _record_at(client, user_id, course_b, datetime(2026, 7, 19, 12, tzinfo=timezone.utc), 7200)
    data = client.get(f'/api/v1/statistics/overview?days=30&course_id={course_a}&end_date=2026-07-19', headers=auth_headers).json()['data']
    assert len(data['daily']) == 30 and data['daily'][0]['date'] == '2026-06-20' and data['daily'][-1]['date'] == '2026-07-19'
    assert data['daily'][0]['actual_learning_seconds'] == 0
    assert len(data['heatmap']) == 49 and data['heatmap'][0]['date'] == '2026-06-01' and data['heatmap'][-1]['date'] == '2026-07-19'
    assert data['summary']['longest_streak_days'] == 3
    assert data['heatmap'][-1]['learning_seconds'] == 600


def test_statistics_efficient_period_threshold_ordering_and_timezone(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_id = _course(client, auth_headers, 'Period course'); question_id = _question(client, course_id, 'period')
    for index in range(2):
        _attempt_at(client, user_id, course_id, question_id, f'two-{index}', datetime(2026, 7, 19, 12, tzinfo=timezone.utc), True)
    initial = client.get(f'/api/v1/statistics/overview?days=7&course_id={course_id}&end_date=2026-07-19', headers=auth_headers).json()['data']['summary']
    assert initial['efficient_period'] is None
    _attempt_at(client, user_id, course_id, question_id, 'three', datetime(2026, 7, 19, 12, tzinfo=timezone.utc), True)
    for index, correct in enumerate((True, True, True, False)):
        _attempt_at(client, user_id, course_id, question_id, f'better-{index}', datetime(2026, 7, 19, 14, tzinfo=timezone.utc), correct)
    period = client.get(f'/api/v1/statistics/overview?days=7&course_id={course_id}&end_date=2026-07-19', headers=auth_headers).json()['data']['summary']['efficient_period']
    assert period == {'label': '20:00–22:00', 'start_hour': 20, 'end_hour': 22, 'attempts': 3, 'correct': 3, 'accuracy': 1.0}


def test_statistics_excludes_other_users_and_archived_course_data(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); active_course = _course(client, auth_headers, 'Visible'); archived_course = _course(client, auth_headers, 'Archived')
    _record_at(client, user_id, active_course, datetime(2026, 7, 19, 12, tzinfo=timezone.utc), 600)
    _record_at(client, user_id, archived_course, datetime(2026, 7, 19, 12, tzinfo=timezone.utc), 7200)
    archived_question = _question(client, archived_course, 'archived-question')
    _attempt_at(client, user_id, archived_course, archived_question, 'archived', datetime(2026, 7, 19, 12, tzinfo=timezone.utc), True)
    _active_plan_tasks(client, user_id, archived_course, [(date(2026, 7, 19), 'completed')])
    other_headers = _other(client); other_user = client.get('/api/v1/users/me', headers=other_headers).json()['data']['id']; other_course = _course(client, other_headers, 'Other')
    _record_at(client, other_user, other_course, datetime(2026, 7, 19, 12, tzinfo=timezone.utc), 3600)
    with client.app.state.database.session_factory() as db:
        db.get(Course, archived_course).archived = True; db.commit()
    data = client.get('/api/v1/statistics/overview?days=7&end_date=2026-07-19', headers=auth_headers).json()['data']
    assert data['summary']['total_learning_seconds'] == 600 and data['summary']['practice_attempts'] == 0 and data['summary']['task_total'] == 0
    assert [item['course_name'] for item in data['course_distribution']] == ['Visible']
    assert data['daily'][-1]['actual_learning_seconds'] == 600 and data['heatmap'][-1]['learning_seconds'] == 600


def test_statistics_csv_daily_matches_overview_and_blank_accuracy(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_id = _course(client, auth_headers, '=CSV course')
    _record_at(client, user_id, course_id, datetime(2026, 7, 19, 12, tzinfo=timezone.utc), 1800)
    overview = client.get(f'/api/v1/statistics/overview?days=30&course_id={course_id}&end_date=2026-07-19', headers=auth_headers).json()['data']
    response = client.get(f'/api/v1/statistics/export.csv?days=30&course_id={course_id}&end_date=2026-07-19', headers=auth_headers)
    rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert len(rows) == 30 and rows[0]['日期'] == overview['daily'][0]['date'] and rows[-1]['日期'] == overview['daily'][-1]['date']
    assert rows[0]['练习正确率'] == '' and rows[-1]['实际学习分钟'] == '30.0'
    assert rows[-1]['课程范围'] == "'=CSV course"


def test_statistics_efficient_period_uses_count_then_earlier_hour_for_ties(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_id = _course(client, auth_headers, 'Period tiebreak'); question_id = _question(client, course_id, 'period-tiebreak')
    for index, correct in enumerate((True, True, True, False)):
        _attempt_at(client, user_id, course_id, question_id, f'early-{index}', datetime(2026, 7, 19, 12, tzinfo=timezone.utc), correct)
    for index, correct in enumerate((True, True, True, True, True, True, False, False)):
        _attempt_at(client, user_id, course_id, question_id, f'count-{index}', datetime(2026, 7, 19, 14, tzinfo=timezone.utc), correct)
    period = client.get(f'/api/v1/statistics/overview?days=7&course_id={course_id}&end_date=2026-07-19', headers=auth_headers).json()['data']['summary']['efficient_period']
    assert period['start_hour'] == 22 and period['accuracy'] == 0.75 and period['attempts'] == 8
    for index, correct in enumerate((True, True, True, True, True, True, False, False)):
        _attempt_at(client, user_id, course_id, question_id, f'later-{index}', datetime(2026, 7, 19, 16, tzinfo=timezone.utc), correct)
    period = client.get(f'/api/v1/statistics/overview?days=7&course_id={course_id}&end_date=2026-07-19', headers=auth_headers).json()['data']['summary']['efficient_period']
    assert period['start_hour'] == 22


def test_statistics_insights_are_stable_and_never_predict(client: TestClient, auth_headers: dict):
    user_id = _user_id(client); course_id = _course(client, auth_headers, 'Insight course')
    _record_at(client, user_id, course_id, datetime(2026, 7, 19, 12, tzinfo=timezone.utc), 600)
    first = client.get('/api/v1/statistics/overview?days=7&end_date=2026-07-19', headers=auth_headers).json()['data']['insights']
    second = client.get('/api/v1/statistics/overview?days=7&end_date=2026-07-19', headers=auth_headers).json()['data']['insights']
    rendered = str(first)
    assert first == second and 1 <= len(first) <= 3
    assert all(word not in rendered for word in ('AI生成', '预计提升', '预测', '留存率'))
