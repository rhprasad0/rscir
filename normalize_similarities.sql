-- Yeah this is poorly written but w/e

with zomg_query as (
	with image_query as (
		with img_mean as (
			with image_query as (
				select embedding from rscir_images ri where ri.filename = 'tenniscourt723.jpg'
			)
			select avg(
				(embedding <#> (select * from image_query)) * -1 
			)
			from rscir_images
		),
		img_std as (
			with image_query as (
				select embedding from rscir_images ri where ri.filename = 'tenniscourt723.jpg'
			)
			select stddev(
				(embedding <#> (select * from image_query)) * -1 
			)
			from rscir_images
		),
		img_similarity as (
			with image_query as (
				select embedding from rscir_images ri where ri.filename = 'tenniscourt723.jpg'
			)
			select *, (
				(embedding <#> (select * from image_query)) * -1 
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
				select embedding from rscir_words rw  where rw.word = 'red'
			)
			select avg(
				(embedding <#> (select * from text_query)) * -1
			) from rscir_images ri
		),
		text_std as (
			with text_query as (
				select embedding from rscir_words rw  where rw.word = 'red'
			)
			select stddev(
				(embedding <#> (select * from text_query)) * -1
			) from rscir_images ri
		),
		text_similarity as (
			with text_query as (
				select embedding from rscir_words rw  where rw.word = 'red'
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
select *,
	(0.4 * img_sim_norm) + (0.6 * txt_sim_norm) as weighted_sim -- lambda=0.6
from zomg_query
order by weighted_sim desc
limit 3;