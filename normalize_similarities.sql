-- The whole shebang
with mean as (
	with image_query as (
		select embedding from rscir_images ri where ri.filename = 'tenniscourt723.jpg'
	)
	select avg(
		(embedding <#> (select * from image_query)) * -1 
	)
	from rscir_images
),
std as (
	with image_query as (
		select embedding from rscir_images ri where ri.filename = 'tenniscourt723.jpg'
	)
	select stddev(
		(embedding <#> (select * from image_query)) * -1 
	)
	from rscir_images
),
similarity as (
	with image_query as (
		select embedding from rscir_images ri where ri.filename = 'tenniscourt723.jpg'
	)
	select (
		(embedding <#> (select * from image_query)) * -1 
	) as similarity
	from rscir_images ri order by similarity desc
)
select similarity, 
	(select * from mean) as mean,
	(select * from std) as std,
	0.5 * (
		1 + erf(
			(similarity - (select * from mean)) / (sqrt(2) * (select * from std))
		)
	) as normalized_similarities
from similarity;