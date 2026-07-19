from fastapi.testclient import TestClient
from sqlalchemy import func, select
from backend.app.models import KnowledgeMastery, KnowledgePoint, LearningRecord, PracticeAttempt, WrongQuestionEntry

def _course(c:TestClient,h:dict,name='Machine Learning'):
    return c.post('/api/v1/courses',headers=h,json={'name':name}).json()['data']['id']
def _other(c:TestClient):
    c.post('/api/v1/auth/register',json={'email':'practice-other@example.com','password':'practice-password','display_name':'Other'})
    return {'Authorization':f"Bearer {c.post('/api/v1/auth/login',json={'email':'practice-other@example.com','password':'practice-password'}).json()['data']['access_token']}"}
def _question(c,h,course):
    assert c.post(f'/api/v1/courses/{course}/practice/questions/bootstrap',headers=h).status_code==200
    return c.get(f'/api/v1/courses/{course}/practice/questions',headers=h).json()['data']['items'][0]

def test_bootstrap_attempt_wrong_book_and_idempotency(client:TestClient,auth_headers:dict):
    course=_course(client,auth_headers)
    with client.app.state.database.session_factory() as db:
        db.add(KnowledgePoint(course_id=course,name='Gradient descent',description='Optimize a loss function',difficulty='intermediate'));db.commit()
    first=client.post(f'/api/v1/courses/{course}/practice/questions/bootstrap',headers=auth_headers).json()['data']; assert first['created_count']==1
    assert client.post(f'/api/v1/courses/{course}/practice/questions/bootstrap',headers=auth_headers).json()['data']['created_count']==0
    question=_question(client,auth_headers,course); assert 'correct_option' not in question and 'Gradient descent' in question['stem']
    bad={'submission_id':'practice-submission-001','selected_option':'B','elapsed_seconds':12}
    result=client.post(f'/api/v1/courses/{course}/practice/questions/{question["id"]}/attempts',headers=auth_headers,json=bad);assert result.status_code==200 and not result.json()['data']['is_correct']
    replay=client.post(f'/api/v1/courses/{course}/practice/questions/{question["id"]}/attempts',headers=auth_headers,json=bad);assert replay.json()['data']['idempotent_replay']
    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(PracticeAttempt))==1; mastery=db.scalar(select(KnowledgeMastery));assert mastery.attempts==1 and mastery.correct_attempts==0
        assert db.scalar(select(func.count()).select_from(LearningRecord).where(LearningRecord.record_type=='practice'))==1; entry=db.scalar(select(WrongQuestionEntry));assert entry.wrong_count==1
    book=client.get(f'/api/v1/courses/{course}/wrong-book',headers=auth_headers).json()['data'];assert book['summary']['pending']==1 and book['items'][0]['question']['correct_option']=='A'
    entry=book['items'][0]['id'];assert client.patch(f'/api/v1/courses/{course}/wrong-book/{entry}',headers=auth_headers,json={'status':'mastered'}).status_code==200
    assert client.get(f'/api/v1/courses/{course}/practice/questions?mode=wrong',headers=auth_headers).json()['data']['total']==0

def test_practice_course_and_user_isolation(client:TestClient,auth_headers:dict):
    a=_course(client,auth_headers,'Course A');b=_course(client,auth_headers,'Course B');other=_other(client)
    with client.app.state.database.session_factory() as db: db.add(KnowledgePoint(course_id=a,name='A point'));db.commit()
    q=_question(client,auth_headers,a)
    assert client.post(f'/api/v1/courses/{b}/practice/questions/{q["id"]}/attempts',headers=auth_headers,json={'submission_id':'cross-course-001','selected_option':'A','elapsed_seconds':1}).status_code==404
    assert client.get(f'/api/v1/courses/{a}/practice/questions',headers=other).status_code==404
    assert client.post(f'/api/v1/courses/{a}/practice/questions/{q["id"]}/attempts',headers=auth_headers,json={'submission_id':'bad-option-001','selected_option':'Z','elapsed_seconds':1}).status_code==422
