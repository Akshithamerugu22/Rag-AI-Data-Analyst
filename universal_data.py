import io,json,re
from pathlib import Path
import pandas as pd
from pypdf import PdfReader
TABLE_EXT=('.csv','.xlsx','.xls','.tsv','.json','.parquet')
def clean_columns(df):
    df=df.copy(); seen={}; out=[]
    for c in df.columns:
        x=re.sub(r'[^a-zA-Z0-9_]+','_',str(c).strip()).strip('_').lower() or 'column'; seen[x]=seen.get(x,0)+1; out.append(x if seen[x]==1 else f'{x}_{seen[x]}')
    df.columns=out; return df
def infer_types(df):
    df=df.copy()
    for c in df.columns:
        if df[c].dtype=='object':
            dt=pd.to_datetime(df[c],errors='coerce')
            if len(df) and dt.notna().mean()>=.90: df[c]=dt; continue
            num=pd.to_numeric(df[c].astype(str).str.replace(',','',regex=False),errors='coerce')
            if len(df) and num.notna().mean()>=.95: df[c]=num
    return df
def load_table(uploaded):
    ext=Path(uploaded.name).suffix.lower(); raw=uploaded.getvalue()
    if ext=='.csv': df=pd.read_csv(io.BytesIO(raw),low_memory=False)
    elif ext=='.tsv': df=pd.read_csv(io.BytesIO(raw),sep='\t',low_memory=False)
    elif ext in ('.xlsx','.xls'):
        parts=[]
        for sheet,x in pd.read_excel(io.BytesIO(raw),sheet_name=None).items():
            if len(x): x=clean_columns(x); x['_source_sheet']=sheet; parts.append(x)
        if not parts: raise ValueError('No non-empty Excel sheets.');
        df=pd.concat(parts,ignore_index=True,sort=False)
    elif ext=='.json':
        obj=json.loads(raw.decode('utf-8')); obj=obj.get('data',obj) if isinstance(obj,dict) else obj; df=pd.DataFrame(obj)
    elif ext=='.parquet': df=pd.read_parquet(io.BytesIO(raw))
    else: raise ValueError('Unsupported table format.')
    return infer_types(clean_columns(df))
def infer_role(s):
    if pd.api.types.is_datetime64_any_dtype(s): return 'date/time'
    if pd.api.types.is_numeric_dtype(s): return 'numeric measure'
    return 'high-cardinality / possible ID' if s.nunique(dropna=True)/max(len(s),1)>.90 else 'categorical dimension'
def profile_dataset(df):
    lines=[f'Rows: {len(df):,}',f'Columns: {len(df.columns):,}',f'Duplicate rows: {df.duplicated().sum():,}',f'Missing cells: {int(df.isna().sum().sum()):,}','Columns:']
    for c in df.columns:
        s=df[c]; lines.append(f'- {c}: dtype={s.dtype}; role={infer_role(s)}; missing={int(s.isna().sum()):,}; unique={s.nunique(dropna=True):,}; examples={s.dropna().astype(str).head(3).tolist()}')
    return '\n'.join(lines)
def make_documents(df,source):
    docs=[{'text':f'DATASET: {source}\n{profile_dataset(df)}','metadata':{'kind':'profile'}}]
    if len(df):
        sample=df.sample(min(1000,len(df)),random_state=42)
        for i in range(0,len(sample),50): docs.append({'text':f'DATASET: {source}\nSAMPLE ROWS\n{sample.iloc[i:i+50].to_csv(index=False)}','metadata':{'kind':'sample_rows'}})
    return docs
def ingest_files(uploads):
    tables={}; documents={}
    for u in uploads:
        ext=Path(u.name).suffix.lower()
        if ext in TABLE_EXT: tables[u.name]=load_table(u); documents[u.name]=make_documents(tables[u.name],u.name)
        elif ext=='.pdf':
            docs=[]
            for i,p in enumerate(PdfReader(io.BytesIO(u.getvalue())).pages,1):
                t=p.extract_text() or ''
                if t.strip(): docs.append({'text':t[:12000],'metadata':{'kind':'pdf_page','page':i}})
            documents[u.name]=docs
        else: raise ValueError(f'{u.name}: unsupported file type.')
    return {'tables':tables,'documents':documents}
def dataset_summary(workspace):
    rows=[]
    for name,df in workspace['tables'].items(): rows.append({'dataset':name,'rows':len(df),'columns':len(df.columns),'numeric_columns':len(df.select_dtypes(include='number').columns),'date_columns':sum(pd.api.types.is_datetime64_any_dtype(df[c]) for c in df.columns),'missing_cells':int(df.isna().sum().sum()),'duplicate_rows':int(df.duplicated().sum())})
    return pd.DataFrame(rows)
