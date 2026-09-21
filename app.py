import os
import streamlit as st
from dotenv import load_dotenv
from universal_data import ingest_files, profile_dataset, dataset_summary
from rag_engine import RAGEngine
from query_planner import QueryPlanner
from report_generator import create_excel_report, create_pdf_report

load_dotenv(); st.set_page_config(page_title='Universal RAG AI Data Analyst',page_icon='📊',layout='wide')
st.title('📊 Universal RAG AI Data Analyst'); st.caption('Schema-independent natural-language analytics over uploaded data.')
for k,v in [('workspace',None),('rag',RAGEngine()),('planner',QueryPlanner(os.getenv('GEMINI_API_KEY',''))),('messages',[]),('last_result',None)]:
    if k not in st.session_state: st.session_state[k]=v
with st.sidebar:
    st.header('Upload')
    uploads=st.file_uploader('CSV • Excel • TSV • JSON • Parquet • PDF',type=['csv','xlsx','xls','tsv','json','parquet','pdf'],accept_multiple_files=True)
    if st.button('🚀 Process files',type='primary',disabled=not uploads):
        with st.spinner('Loading, profiling and indexing...'):
            ws=ingest_files(uploads); st.session_state.workspace=ws; st.session_state.rag.reset()
            for source,docs in ws['documents'].items(): st.session_state.rag.add_documents(docs,source)
            st.session_state.messages=[]; st.session_state.last_result=None
        st.success('Workspace ready.')
    key=st.text_input('Gemini API key (optional)',value=os.getenv('GEMINI_API_KEY',''),type='password')
    if key: st.session_state.planner=QueryPlanner(key)
    if st.session_state.last_result:
        if st.button('📊 Prepare Excel report'): st.session_state.excel_path=create_excel_report(st.session_state.last_result)
        if st.button('📄 Prepare PDF report'): st.session_state.pdf_path=create_pdf_report(st.session_state.last_result)
        if st.session_state.get('excel_path'):
            with open(st.session_state.excel_path,'rb') as f: st.download_button('Download Excel',f,file_name='AI_Data_Analyst_Report.xlsx')
        if st.session_state.get('pdf_path'):
            with open(st.session_state.pdf_path,'rb') as f: st.download_button('Download PDF',f,file_name='AI_Data_Analyst_Report.pdf')
if not st.session_state.workspace:
    st.info('Upload one or more files to start.')
    st.markdown('''### Designed for unfamiliar datasets
The system automatically detects numeric measures, categorical dimensions, dates, identifiers, missing values and duplicates.

### Example questions
- What is the total of the main numeric measure?
- Which category has the highest average value?
- Show the monthly trend.
- Compare groups.
- Find outliers.
- Which columns have missing values?
- Give me the main insights.''')
    st.stop()
ws=st.session_state.workspace; st.subheader('📁 Workspace'); st.dataframe(dataset_summary(ws),use_container_width=True)
with st.expander('Automatic schema profiles'):
    for name,table in ws['tables'].items(): st.markdown(f'### {name}'); st.code(profile_dataset(table),language='text')
st.divider(); st.subheader('💬 Ask your data')
for m in st.session_state.messages:
    with st.chat_message(m['role']):
        st.markdown(m['content'])
        if m.get('table') is not None: st.dataframe(m['table'],use_container_width=True)
        if m.get('chart') is not None: st.plotly_chart(m['chart'],use_container_width=True)
        if m.get('sql'):
            with st.expander('🔐 Generated SQL'): st.code(m['sql'],language='sql')
q=st.chat_input('Ask a question about any uploaded dataset...')
if q:
    st.session_state.messages.append({'role':'user','content':q})
    with st.chat_message('user'): st.markdown(q)
    with st.chat_message('assistant'):
        with st.spinner('Planning → validating → querying → retrieving → explaining...'):
            try:
                result=st.session_state.planner.answer(q,ws,st.session_state.rag); st.session_state.last_result=result; st.markdown(result['answer'])
                if result.get('table') is not None: st.dataframe(result['table'],use_container_width=True)
                if result.get('chart') is not None: st.plotly_chart(result['chart'],use_container_width=True)
                if result.get('sql'):
                    with st.expander('🔐 Generated SQL'): st.code(result['sql'],language='sql')
            except Exception as e: result={'answer':f'Analysis failed: {e}'}; st.error(result['answer'])
    st.session_state.messages.append({'role':'assistant','content':result.get('answer',''),'table':result.get('table'),'chart':result.get('chart'),'sql':result.get('sql')})
