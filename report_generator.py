from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
def create_excel_report(result):
    p=Path('/tmp/AI_Data_Analyst_Report.xlsx'); wb=Workbook(); ws=wb.active; ws.title='Analysis'; ws.append(['Question',result.get('question','')]); ws.append(['Answer',result.get('answer','')]); ws.append(['SQL',result.get('sql','')]); ws.append([]); t=result.get('table')
    if isinstance(t,pd.DataFrame):
        for row in dataframe_to_rows(t,index=False,header=True):ws.append(row)
    wb.save(p); return p
def create_pdf_report(result):
    p=Path('/tmp/AI_Data_Analyst_Report.pdf'); doc=SimpleDocTemplate(str(p),pagesize=A4); styles=getSampleStyleSheet(); story=[Paragraph('Universal RAG AI Data Analyst Report',styles['Title']),Spacer(1,10),Paragraph('Question: '+str(result.get('question','')),styles['Heading2']),Paragraph(str(result.get('answer','')).replace('\n','<br/>'),styles['BodyText']),Spacer(1,10)]; t=result.get('table')
    if isinstance(t,pd.DataFrame) and not t.empty:
        data=[list(t.columns)]+t.head(25).astype(str).values.tolist(); tb=Table(data,repeatRows=1); tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.25,colors.grey),('FONTSIZE',(0,0),(-1,-1),7)])); story.append(tb)
    doc.build(story); return p
