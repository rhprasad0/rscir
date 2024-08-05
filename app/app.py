import psycopg
from flask import Flask, render_template

app = Flask(__name__)

def get_db_connection():
    conn = psycopg.connect(
    host="",
    user="",
    password="",
    dbname="",
    port=5432,
    autocommit=True
    )

    return conn

def composite_search():

    conn = get_db_connection()
    with conn.cursor() as cur:
        
        res = cur.execute('select * from rscir_images ri order by random() limit 1;').fetchone()

        query_img_filename = res[0]
        query_img_url = res[1]
        img_query = res[2]

        res = cur.execute('select word from rscir_words rw;').fetchall()

        words = []
        for word in res:
            words.append(word[0])


        composite_search_results = []

        for word in words:
            res = cur.execute(
                f"""
                    with zomg_query as (
                        with image_query as (
                            with img_mean as (
                                select avg(
                                    (embedding <#> '{img_query}') * -1 
                                )
                                from rscir_images
                            ),
                            img_std as (
                                select stddev(
                                    (embedding <#> '{img_query}') * -1 
                                )
                                from rscir_images
                            ),
                            img_similarity as (
                                with image_query as (
                                    select embedding from rscir_images ri where ri.filename = '{query_img_filename}'
                                )
                                select *, (
                                    (embedding <#> '{img_query}') * -1 
                                ) as img_similarity
                                from rscir_images ri order by img_similarity desc
                            )
                            select *, 
                                (select * from img_mean) as img_mean,
                                (select * from img_std) as img_std,
                                0.5 * (
                                    1 + erf(
                                        (img_similarity - (select * from img_mean)) / (sqrt(2) * (select * from img_std))
                                    )
                                ) as img_sim_norm
                            from img_similarity
                        ),
                            text_query as (
                            with text_mean as (
                                with text_query as (
                                    select embedding from rscir_words rw  where rw.word = '{word}'
                                )
                                select avg(
                                    (embedding <#> (select * from text_query)) * -1
                                ) from rscir_images ri
                            ),
                            text_std as (
                                with text_query as (
                                    select embedding from rscir_words rw  where rw.word = '{word}'
                                )
                                select stddev(
                                    (embedding <#> (select * from text_query)) * -1
                                ) from rscir_images ri
                            ),
                            text_similarity as (
                                with text_query as (
                                    select embedding from rscir_words rw  where rw.word = '{word}'
                                )
                                select *, (
                                    (embedding <#> (select * from text_query)) * -1 
                                ) as txt_sim
                                from rscir_images ri order by txt_sim desc
                            )
                            select *, 
                                (select * from text_mean) as text_mean,
                                (select * from text_std) as text_std,
                                0.5 * (
                                    1 + erf(
                                        (txt_sim - (select * from text_mean)) / (sqrt(2) * (select * from text_std))
                                    )
                                ) as txt_sim_norm
                            from text_similarity
                        )
                        select 
                            image_query.filename,
                            image_query.url,
                            image_query.img_sim_norm,
                            text_query.txt_sim_norm
                        from image_query join text_query on image_query.filename=text_query.filename
                    )
                    select url,
                        (0.4 * img_sim_norm) + (0.6 * txt_sim_norm) as weighted_sim -- lambda=0.6
                    from zomg_query
                    order by weighted_sim desc
                    limit 1;
                """
            ).fetchone()

            result_url = res[0]
            result_sim = res[1]
            composite_search_results.append((word, result_url, result_sim))

    return query_img_url, composite_search_results


@app.route('/')
def index():
    query_img, search_results = composite_search()
    return render_template('index.html', 
                           query_img=query_img, 
                           search_results=search_results
                           )