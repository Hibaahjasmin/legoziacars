import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

supabase_url = os.getenv("DATABASE_URL")
print("Targeting Database URL:", supabase_url)

# Import models to populate db.metadata
import run
from run import db

if supabase_url:
    engine = create_engine(supabase_url)
    db.metadata.create_all(bind=engine)
    print("SUCCESS: Tables built directly on Supabase!")
else:
    print("ERROR: DATABASE_URL is missing in your .env file!")