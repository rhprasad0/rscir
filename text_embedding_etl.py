from utils import *
from pgvector.psycopg import register_vector
import psycopg


MODEL_NAME = "remoteclip"

words = [
    "blue",
    "green",
    "brown",
    "gray",
    "red",
    "purple",
    "white",
    "yellow",
    "water",
    "concrete",
    "sparse",
    "dense",
    "full",
    "empty",
    "one",
    "two",
    "three",
    "four",
    "two-halfs",
    "cross",
    "round",
    "oval",
    "rectangular",
    "kidney-shaped",
    "curved",
    "straight"
]
table_name = "rscir_words"
dimensions = 768 # this is just what we get from RSCIS

word_embedding_tuples = []
embeddings = []

# Load model and tokenizer
model, _, tokenizer = load_model(MODEL_NAME, 'ViT-L-14')

for word in words:
    text = tokenizer(word).to('cuda')
    text_feature = model.encode_text(text)
    text_feature = (text_feature / text_feature.norm(dim=-1, keepdim=True)).squeeze().detach().tolist()
    embeddings.append(text_feature)

word_embedding_tuples.extend(zip(words, embeddings))
print("Embeddings generated!")
print()

# enable extension
conn = psycopg.connect(
    host="",
    user="",
    password="",
    dbname="",
    port=5432,
    autocommit=True,
)

with conn.cursor() as cursor:
    cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
    register_vector(conn)

    # create table
    cursor.execute(f'DROP TABLE IF EXISTS {table_name}')
    cursor.execute(
        f"""
            CREATE TABLE {table_name} (
            word text,
            embedding vector({dimensions})
            );
        """
    )

    cursor.executemany(f"INSERT INTO {table_name} VALUES(%s,%s)", word_embedding_tuples)

print("Embeddings inserted into Postgres! :-D")