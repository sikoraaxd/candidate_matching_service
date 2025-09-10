from io import BytesIO
from dotenv import load_dotenv

import os
import re
import requests
import pandas as pd
import streamlit as st
from streamlit import session_state as ss
from ranker import get_rating, CANDIDATE_RANKING_PROMPT, INTERVIEWER_RANKING_PROMPT

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, APIError


load_dotenv()

# Google Spreadsheets API Service account key
SERVICE_ACCOUNT_INFO = {
    "type": os.getenv('gs_type'),
    "project_id": os.getenv('gs_project_id'),
    "private_key_id": os.getenv('gs_private_key_id'),
    "private_key": os.getenv('gs_private_key'),
    "client_email": os.getenv('gs_client_email'),
    "client_id": os.getenv('gs_client_id'),
    "auth_uri": os.getenv('gs_auth_uri'),
    "token_uri": os.getenv('gs_token_uri'),
    "auth_provider_x509_cert_url": os.getenv('gs_auth_provider_x509_cert_url'),
    "client_x509_cert_url": os.getenv('gs_client_x509_cert_url'),
    "universe_domain": os.getenv('gs_universe_domain')
}

# Permitted zones
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Google Spreadsheets authorization 
creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
client = gspread.authorize(creds)

    
# ---------------------------
# UI
# ---------------------------
ss.setdefault('completion_bytes', b'')
st.set_page_config(page_title="Ранжировщик кандидатов", layout="wide")

st.markdown(
    """
        <style>
            .stButton > button {
                float: right;
            }
        </style>
    """,
    unsafe_allow_html=True
)

st.title("🔎 Подбор кандидатов и интервьюеров")

# Общее поле ввода требований
requirements = st.text_area(
    "✍️ Введите требования вакансии:", 
    height=400, 
    key=f"requirements"
)

# Вкладки
tab_candidates, tab_interviewers = st.tabs(["Подбор кандидата", "Подбор интервьюера"])



# Рендеринг вкладки подбора кандидатов
with tab_candidates:
    title = "Поиск кандидата"
    key_prefix="candidate"

    subheader_column, rank_button_column = st.columns([1, 1])
    subheader_column.subheader(title)

    # Открыть таблицу по названию
    departments_map = {
        '1C': 'Карта компетенций 1с',
        'Data Platform': 'Карта компетенций DP'
    }

    selected_department = st.selectbox(
        "📂 Выберите департамент:",
        list(departments_map.keys()),
        key=f"department_direction"
    )

    selected_sheet_name = None
    show_candidates = False
    include_staffing = False
    include_laboratory = False

    if requirements and selected_department:
        try:
            # Получить и отобразить все листы
            
            candidates_spreadsheet = client.open(departments_map[selected_department])
            worksheets = candidates_spreadsheet.worksheets()
            sheet_names = [ws.title for ws in worksheets]                
            selected_sheet_name = st.selectbox(
                "📂 Выберите компетенцию:",
                sheet_names,
                key=f"{key_prefix}_direction"
            )

            show_candidates = st.checkbox(
                "Показать список кандидатов",
                value=True,
                key=f"chk_{key_prefix}s"
            )

            with st.container():
                st.markdown("###### Включить в список кандидатов:")
                include_staffing = st.checkbox("Стаффинг", key=f"chk_{key_prefix}s_staffing")
                include_laboratory = st.checkbox("Лабораторию", key=f"chk_{key_prefix}s_laboratory")

        except SpreadsheetNotFound:
            st.error("Файл не найден или нет доступа!", icon="🚨")
        except APIError as e:
            st.error(f"Ошибка API: {e}", icon="🚨")
    else:
        st.info("Введите требования, чтобы выбрать компетенцию", icon="💡")
    
    # Когда заполнены требования и указано направление - начинается ранжирование
    if requirements and selected_sheet_name:
        candidates_spreadsheet = client.open(departments_map[selected_department])
        candidates_worksheet = candidates_spreadsheet.worksheet(selected_sheet_name)
        candidates_values = candidates_worksheet.get_all_values()
        competentions_df = pd.DataFrame(candidates_values[6:], columns=candidates_values[5])
        competentions_df.columns = ['Навык'] + list(competentions_df.columns[1:])
        unsupported_columns = [column for column in competentions_df.columns if 'Unnamed' in column]
        competentions_df.drop(columns=unsupported_columns, inplace=True)

        empty_competentions_ids = competentions_df[competentions_df['Навык'].str.strip().str.len() == 0].index
        competentions_df.drop(index=empty_competentions_ids, inplace=True)
        competentions_df.dropna(subset='Навык', inplace=True)

        # Удаляю консультантов (консультанты не выступают в качестве кандидатов)
        pattern = r"(cnslt)"    
        cols_to_drop = [col for col in competentions_df.columns if re.search(pattern, col, flags=re.IGNORECASE)]
        competentions_df.drop(columns=cols_to_drop, inplace=True)

        if not include_staffing:
            pattern = r"(staff)"
            
            cols_to_drop = [col for col in competentions_df.columns if re.search(pattern, col, flags=re.IGNORECASE)]
            competentions_df.drop(columns=cols_to_drop, inplace=True)

        if not include_laboratory:
            pattern = r"(laba)"
            
            cols_to_drop = [col for col in competentions_df.columns if re.search(pattern, col, flags=re.IGNORECASE)]
            competentions_df.drop(columns=cols_to_drop, inplace=True)

        if show_candidates:
            st.subheader("Список кандидатов")
            st.dataframe(competentions_df, height=250)

        if rank_button_column.button("🚀 Запустить ранжирование", key=f"btn_{key_prefix}s_rank"):
            # Запрашиваю ранжир
            rating = get_rating(
                requirements=requirements,
                competentions=competentions_df.to_markdown(index=False),
                ranking_prompt=CANDIDATE_RANKING_PROMPT
            )

            # Вывожу результаты
            result_data = []
            for worker in rating:
                result_data.append({
                    'Сотрудник': worker.name,
                    'Рейтинг': f'{worker.rating}%',
                    'Релевантные компетенции': ', '.join(worker.goods),
                    'Что подтянуть': ', '.join(worker.bads)
                })

            st.success("Ранжирование завершено!")
            st.subheader("Результаты ранжирования")
            st.dataframe(pd.DataFrame(result_data), width=1600)


# Рендеринг вкладки подбора интервьюеров
with tab_interviewers:
    title = "Поиск интервьюера"
    key_prefix="interviewer"

    subheader_column, rank_button_column = st.columns([1, 1])
    subheader_column.subheader(title)

    # Открыть таблицу по названию
    interviewers_spreadsheet = client.open("Карта интервьюеров")

    interviewers_selected_sheet_name = None
    show_interviewers = False
    include_consultant = False

    if requirements:
        try:
            # Получить и отобразить все листы
            worksheets = interviewers_spreadsheet.worksheets()
            sheet_names = [ws.title for ws in worksheets]                
            interviewers_selected_sheet_name = st.selectbox(
                "📂 Выберите компетенцию:",
                sheet_names,
                key = f"{key_prefix}_direction"
            )

            show_interviewers = st.checkbox(
                "Показать список интервьюеров",
                value=True,
                key = f"chk_{key_prefix}s"
            )

        except SpreadsheetNotFound:
            st.error("Файл не найден или нет доступа!", icon="🚨")
        except APIError as e:
            st.error(f"Ошибка API: {e}", icon="🚨")
    else:
        st.info("Введите требования, чтобы выбрать компетенцию", icon="💡")
    
    # Когда заполнены требования и указано направление - начинается ранжирование
    if requirements and interviewers_selected_sheet_name and selected_department != '1C':
        #Подгружаем карту интервьюеров
        interviewers_worksheet = interviewers_spreadsheet.worksheet(interviewers_selected_sheet_name)
        interviewers_values = interviewers_worksheet.get_all_values()
        interviewers_df = pd.DataFrame(interviewers_values[1:], columns=interviewers_values[0])
        interviewers_df.dropna(subset='Сотрудник', inplace=True)

        #Подгружаем список кандидатов
        #Todo: Сделать подгрузку 1 раз за весь сеанс
        interviewers_candidates_spreadsheet = client.open(departments_map[selected_department])
        interviewers_candidates_worksheet = interviewers_candidates_spreadsheet.worksheet(interviewers_selected_sheet_name)
        interviewers_candidates_values = interviewers_candidates_worksheet.get_all_values()
        interviewers_competentions_df = pd.DataFrame(interviewers_candidates_values[6:], columns=interviewers_candidates_values[5])

        # Убираем лишних интервьюеров
        interviewers_list = [interviewers_competentions_df.columns[0]] + interviewers_df['Сотрудник'].tolist() #Сотрудник + список из карты интервьюеров
        interviewers_to_drop = [col for col in interviewers_competentions_df.columns if all(intererviewer not in col for intererviewer in interviewers_list)]
        interviewers_competentions_df.drop(columns=interviewers_to_drop, inplace=True)

        # Чистим датафрейм
        interviewers_competentions_df.columns = ['Навык'] + list(interviewers_competentions_df.columns[1:])
        unsupported_columns = [column for column in interviewers_competentions_df.columns if 'Unnamed' in column]
        interviewers_competentions_df.drop(columns=unsupported_columns, inplace=True)
        empty_competentions_ids = interviewers_competentions_df[interviewers_competentions_df['Навык'].str.strip().str.len() == 0].index
        interviewers_competentions_df.drop(index=empty_competentions_ids, inplace=True)
        interviewers_competentions_df.dropna(subset='Навык', inplace=True)

        # Добавляем к именам сотрудников их уровень
        interviewers_competentions_df.columns = [
            col if col == 'Навык' else f"{col} ({interviewers_df[[intr.lower() in col.strip().lower() for intr in interviewers_df['Сотрудник']]].iloc[0]['Уровень']})"
            for col in interviewers_competentions_df.columns
        ]

        if show_interviewers:
            st.subheader("Список интервьюеров")
            st.dataframe(interviewers_competentions_df, height=350)

        if rank_button_column.button("🚀 Запустить ранжирование", key=f"btn_{key_prefix}s_rank"):

            # Запрашиваю ранжир
            interviewers_rating = get_rating(
                requirements=requirements,
                competentions=interviewers_competentions_df.to_markdown(index=False),
                ranking_prompt=INTERVIEWER_RANKING_PROMPT
            )

            # Вывожу результаты
            interviewers_result_data = []
            for worker in interviewers_rating:
                interviewers_result_data.append({
                    'Сотрудник': worker.name,
                    'Рейтинг': f'{worker.rating}%',
                    'Релевантные компетенции': ', '.join(worker.goods),
                    'Что подтянуть': ', '.join(worker.bads)
                })

            st.success("Ранжирование завершено!")
            st.subheader("Результаты ранжирования")
            st.dataframe(pd.DataFrame(interviewers_result_data), width=1600)

    
