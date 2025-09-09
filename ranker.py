from typing import List
from pydantic import BaseModel, Field

import os
from langchain_openai.chat_models import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


CANDIDATE_RANKING_PROMPT = ChatPromptTemplate(messages=[(
    'user',
    '''
        Ниже представлено ОПИСАНИЕ ВАКАНСИИ и ТАБЛИЦА КОМПЕТЕНЦИЙ возможных работников компании.
        Твоя задача для каждого работника компании присвоить РЕЙТИНГ СООТВЕТСТВИЯ данной вакансии.
        А затем отсортировать каждого работника по убыванию РЕЙТИНГА СООТВЕТСТВИЯ.
        ОПИСАНИЕ ВАКАНСИИ:
        {requirements}

        ТАБЛИЦА КОМПЕТЕНЦИЙ:
        {competentions}

        Ответ:
    '''
)])

INTERVIEWER_RANKING_PROMPT = ChatPromptTemplate(messages=[(
    'user',
    '''
        Ниже представлено ОПИСАНИЕ ВАКАНСИИ и ТАБЛИЦА КОМПЕТЕНЦИЙ интервьюеров компании.
        Твоя задача для каждого интервьюера присвоить РЕЙТИНГ СООТВЕТСТВИЯ данной вакансии.
        А затем отсортировать каждого интервьюера по убыванию РЕЙТИНГА СООТВЕТСТВИЯ.
        Обязательно учитывай уровень интервьюера, он прописан в скобках рядом с именем:
        J* - Junior (1, 2, 3)
        M* - Middle (1, 2, 3)
        S* - Senior (1, 2)
        Чем выше цифра рядом с уровнем, тем компетентнее специалист в своем грейде.


        ОПИСАНИЕ ВАКАНСИИ:
        {requirements}

        ТАБЛИЦА КОМПЕТЕНЦИЙ:
        {competentions}

        Ответ:
    '''
)])


# ---------------------------
# Entities
# ---------------------------
class Worker(BaseModel):
    name: str = Field(description='ФИО работника')
    rating: int = Field(description='РЕЙТИНГ СООТВЕТСТИЯ - число от 1 до 100')
    goods: List[str] = Field(description='Компетенции, которые полезны для вакансии. Только названия навыков.')
    bads: List[str] = Field(description='Компетенции, которые нужно подтянуть для вакансии. Только названия навыков.')


class WorkerRating(BaseModel):
    rating: List[Worker] = Field(description='Рейтинг сотрудников в порядке убывания рейтинга')


# ---------------------------
# Ranking
# ---------------------------
def get_rating(requirements: str, competentions: str, ranking_prompt: str) -> WorkerRating:
    llm = ChatOpenAI(
        model=os.getenv('MODEL_NAME'),
        api_key=os.getenv('OPENAI_API_KEY'),
        base_url=os.getenv('OPENAI_API_BASE'),
        temperature=0.0,
        seed=42
    )
    llm = llm.with_structured_output(WorkerRating)

    chain = ranking_prompt | llm
    return chain.invoke({
        'requirements': requirements,
        'competentions': competentions
    }).rating