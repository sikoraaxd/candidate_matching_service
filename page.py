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


# Функция для выбора моды с учетом None
def mode_with_none(row):
    counts = row.value_counts(dropna=False)
    return counts.idxmax()  # самое частое значение, включая None/NaN


# Рендеринг вкладки подбора кандидатов
with tab_candidates:
    title = "Поиск кандидата"
    key_prefix="candidate"

    subheader_column, rank_button_column = st.columns([1, 1])
    subheader_column.subheader(title)

    # Открыть таблицу по названию
    spreadsheet = client.open("Карта компетенций DP")

    selected_sheet_name = None
    show_candidates = False
    include_staffing = False
    include_laboratory = False

    if requirements:
        try:
            # Получить и отобразить все листы
            worksheets = spreadsheet.worksheets()
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
        # Получаем ссылку на экспорт XLSX
        export_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/export?format=xlsx"

        # Делаем запрос с авторизацией
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {creds.token}"})
        response = session.get(export_url)

        # Читаем сразу в pandas
        competentions_df = pd.read_excel(BytesIO(response.content), sheet_name=selected_sheet_name, header=5)
        competentions_df.columns = ['Навык'] + list(competentions_df.columns[1:])
        unsupported_columns = [column for column in competentions_df.columns if 'Unnamed' in column]
        competentions_df.drop(columns=unsupported_columns, inplace=True)
        competentions_df.dropna(how='all', inplace=True)

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
    interviewers_spreadsheet = client.open("Карта интревьюеров")

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

            with st.container():
                st.markdown("###### Включить в список интервьюеров:")
                include_consultant = st.checkbox("Консультанты", key=f"chk_{key_prefix}s_consultant")

        except SpreadsheetNotFound:
            st.error("Файл не найден или нет доступа!", icon="🚨")
        except APIError as e:
            st.error(f"Ошибка API: {e}", icon="🚨")
    else:
        st.info("Введите требования, чтобы выбрать компетенцию", icon="💡")
    
    # Когда заполнены требования и указано направление - начинается ранжирование
    if requirements and interviewers_selected_sheet_name:
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {creds.token}"})

        # 1. Сначала выбираем из таблиц интервьюеров
        interviewers_export_url = f"https://docs.google.com/spreadsheets/d/{interviewers_spreadsheet.id}/export?format=xlsx"
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {creds.token}"})
        response = session.get(interviewers_export_url)

        interviewers_df = pd.read_excel(BytesIO(response.content), sheet_name=interviewers_selected_sheet_name)
        unsupported_columns = [column for column in interviewers_df.columns if 'Unnamed' in column]
        interviewers_df.drop(columns=unsupported_columns, inplace=True)
        interviewers_df.dropna(how='all', inplace=True)

        # 2. А теперь выбираем сотрудников
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {creds.token}"})
        response = session.get(export_url)

        interviewers_competentions_df = pd.read_excel(BytesIO(response.content), sheet_name=interviewers_selected_sheet_name, header=5)
        interviewers_competentions_df.columns = ['Навык'] + list(interviewers_competentions_df.columns[1:])
        unsupported_columns = [column for column in interviewers_competentions_df.columns if 'Unnamed' in column]
        interviewers_competentions_df.drop(columns=unsupported_columns, inplace=True)
        interviewers_competentions_df.dropna(how='all', inplace=True)

        # Удаляю стаффинг и лабораторию (стаффинг и лаборатория не выступают в качестве интервьюеров)
        pattern = r"(staff|laba)"
        cols_to_drop = [col for col in interviewers_competentions_df.columns if re.search(pattern, col, flags=re.IGNORECASE)]
        interviewers_competentions_df.drop(columns=cols_to_drop, inplace=True)

        # 3. Теперь из первого датафрейма удаляем тех сотрудников, что есть во втором
        # Список фамилий из первого df
        names_to_remove = []
        for name in list(interviewers_competentions_df.columns[1:]):
            if name.startswith("cnslt - "):
                names_to_remove.append(name.replace("cnslt - ", ""))
            else:
                names_to_remove.append(name)

        # Фильтруем столбцы второго df
        interviewers_df = interviewers_df[~interviewers_df['Сотрудник'].isin(names_to_remove)]

        if not include_consultant:
            pattern = r"(cnslt)"    
            
            cols_to_drop = [col for col in interviewers_competentions_df.columns if re.search(pattern, col, flags=re.IGNORECASE)]
            interviewers_competentions_df.drop(columns=cols_to_drop, inplace=True)

        for interviewer in interviewers_df['Сотрудник']:
            # Добавляем нового сотрудника справа с мажоритарной компетенцией
            interviewers_competentions_df[interviewer] = interviewers_competentions_df.apply(mode_with_none, axis=1)

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

    