import re,duckdb
class DataEngine:
    def __init__(self,tables):
        self.tables=tables; self.con=duckdb.connect(database=':memory:'); self.aliases={}
        for name,df in tables.items(): self.aliases[name]=self.safe_name(name); self.con.register(self.aliases[name],df)
    @staticmethod
    def safe_name(name): return 't_'+(re.sub(r'[^a-zA-Z0-9_]+','_',name).strip('_').lower() or 'dataset')
    def schema_text(self):
        return '\n\n'.join(f'TABLE "{self.aliases[n]}" [source={n}] COLUMNS: '+', '.join(f'"{c}" ({df[c].dtype})' for c in df.columns) for n,df in self.tables.items())
    def execute(self,sql): return self.con.execute(sql).df()
