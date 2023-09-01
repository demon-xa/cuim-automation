select
  clear_title,
  count(*) as count_issues,
  count(DISTINCT maintenance) as count_unique_maintenance
from
	(
	select
    -- COALESCE(fq.maintenance_entity_id, 0) as maintenance,
    fq.maintenance_entity_id as maintenance,
    case
      when fq.title like '%обновление бт%' then 'обновление бт'
      when fq.title like '%обновление прошивки бт%' then 'обновление бт'
      when fq.title like '%прошивка бт%' then 'обновление бт'
      when fq.title like '%обновление по бт%' then 'обновление бт'
      when fq.title like '%обновление по%' then 'обновление по'
      when fq.title like '%нет пинга до обзорной камеры%' then 'нет пинга до обзорной камеры'
      when fq.title like '%замена ссд%' then 'замена диска'
      when fq.title like '%замена ssd%' then 'замена диска'
      when fq.title like '%расхождение в часовом поясе%' then 'расхождение в часовом поясе'
      when fq.title like '%остановился видеопоток на обзорной камере%' then 'остановился видеопоток на обзорной камере'
  		when fq.title like '%нет пинга в течение%' then 'нет пинга в течение ...'
  		when fq.title like '%запрос из телеграмм группы%' then 'запрос из телеграмм группы'
      when fq.title like '%локальная диагностика%' then 'локальная диагностика'
      when fq.title like '%много брака%' then 'много брака'
      when fq.title like '%очистка%' then 'очистка ОК/РК/...'
      when fq.title like '%наведение%' then 'наведение'
      when fq.title like '%ошибка сертификата%' then 'ошибка сертификата'
      when fq.title like '%отсутствуют нарушения%' then 'отсутствуют нарушения'
      else fq.title
    end as clear_title
  from
    (
      select
        i.sequential_id,
      	i.maintenance_entity_id,
        i.title as dirty_title,
        lower(trim(both from 
          regexp_replace(
            regexp_replace(
              regexp_replace(
                i.title,'(\-\s+)?(?<!\.)[a-z0-9]+(?=\d)([^\s]+)?(\s+\-?)?|\d+(?=[\.])[\d\.]+|ПСМ[^\s]+','','ig'
              ), '(\s+)?на(\s+)?$', '', 'ig'
            ), '\s+', ' ', 'ig'
          )
        )) as title,
        g.name as group,
-- 				l.id log_id,
-- 				l.trackable_id,
-- 				l.assignee_was_id,
-- 				l.assignee_now_id,
-- 				l.assignee_group_was_id,
-- 				l.assignee_group_now_id,
        l.created_at as log_t,
        i.created_at as issues_t,
        l.created_at - i.created_at as delta_t
      from
        issues i,
        issue_assignee_logs l,
        groups g
      where
        i.id = l.trackable_id
        and l.assignee_group_now_id = g.id
        and upper(g.name) like '%{search_group}%'
        and l.assignee_group_was_id is null
        -- время события создания в issue_assignee_logs может незначительно отличаться от времени создания задачи в issues 
        and l.created_at - i.created_at < '00:01:00'
        and DATE_TRUNC('week', i.created_at) >= '{timeStart}'
        and DATE_TRUNC('week', i.created_at) <= '{timeEnd}'
      order by l.created_at asc
    ) as fq
  where
    fq.title <> ''
 ) as sq
 group by clear_title
 order by count_issues desc