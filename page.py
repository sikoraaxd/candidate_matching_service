import streamlit as st
from streamlit import session_state as ss
from dotenv import load_dotenv
load_dotenv()
import pandas as pd
from langchain_openai.chat_models import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import List
import os

st.set_page_config(layout='wide', page_title='Ранжировщик сотрудников')
ss.setdefault('completion_bytes', b'')

class Worker(BaseModel):
    name: str = Field(description='ФИО работника')
    rating: int = Field(description='РЕЙТИНГ СООТВЕТСТИЯ - число от 1 до 100')
    goods: List[str] = Field(description='Компетенции, которые полезны для вакансии. Только названия навыков.')
    bads: List[str] = Field(description='Компетенции, которые нужно подтянуть для вакансии. Только названия навыков.')

class WorkerRating(BaseModel):
    rating: List[Worker] = Field(description='Рейтинг сотрудников в порядке убывания рейтинга')

RANKING_PROMPT = ChatPromptTemplate(messages=[
    (
        'user',
        '''\
Ниже представлено ОПИСАНИЕ ВАКАНСИИ и ТАБЛИЦА КОМПЕТЕНЦИЙ возможных работников компании.
Твоя задача для каждого работника компании присвоить РЕЙТИНГ СООТВЕТСТВИЯ данной вакансии.
ОПИСАНИЕ ВАКАНСИИ:
{requiremets}

ТАБЛИЦА КОМПЕТЕНЦИЙ:
{competentions}

Ответ:'''
    )
])

def get_rating(requiremets_text: str, competentions: str) -> WorkerRating:
    llm = ChatOpenAI(
        model=os.getenv('MODEL_NAME'),
        api_key=os.getenv('OPENAI_API_KEY'),
        base_url=os.getenv('OPENAI_API_BASE'),
        temperature=0.0,
        seed=42
    )
    llm = llm.with_structured_output(WorkerRating)

    chain = RANKING_PROMPT | llm
    return chain.invoke({
        'requiremets': requiremets_text,
        'competentions': competentions
    }).rating


files_cols = st.columns(2)

requiremets_text = files_cols[0].text_area('Впишите описание вакансии', height=350)
competentions_file = files_cols[1].file_uploader('Прикрепите таблицу с компетенциями', type='xlsx')
if competentions_file and requiremets_text:
    ss.competentions_bytes = competentions_file.read()
    competentions_excel = pd.ExcelFile(ss.competentions_bytes)
    sheet_name = files_cols[1].selectbox('Выберите направление:', competentions_excel.sheet_names)
    competentions_df = pd.read_excel(ss.competentions_bytes, sheet_name=sheet_name, header=5)
    competentions_df.columns = ['Навык'] + list(competentions_df.columns[1:])
    unsupported_columns = [column for column in competentions_df.columns if 'Unnamed' in column]
    competentions_df.drop(columns=unsupported_columns, inplace=True)
    competentions_df.dropna(how='all', inplace=True)
    st.dataframe(competentions_df, height=250)
    rating = get_rating(
        requiremets_text=requiremets_text,
        competentions=competentions_df.to_markdown(index=False)
    )
    st.markdown('# Результаты:')
    result_data = []
    for worker in rating:
        result_data.append({
            'Сотрудник': worker.name,
            'Рейтинг': f'{worker.rating}%',
            'Релевантные компетенции': ', '.join(worker.goods),
            'Что подтянуть': ', '.join(worker.bads)
        })
    st.dataframe(pd.DataFrame(result_data), width=1600)