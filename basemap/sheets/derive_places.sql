-- The key-camera intersections' centres in places.json, from OpenStreetMap (core.osm_way and core.osm_node: the
-- osm_valley load of the held extract). Each camera's own position (core.camera, from ACHD's list) only picks which
-- crossing it watches; it isn't written anywhere. Read-only; run on the scratch database:
--
--   data/dev/scratch-run.sh psql -A -F'|' -f - < basemap/sheets/derive_places.sql
--
-- Rules: cross = the centroid of the crossings of roads matching a and b (name or ref, as a regular expression)
-- within near_m of the camera, in the cluster (cluster_m) nearest it; signal = the nearest traffic_signals node;
-- roundabout = the centre of the nearest junction=roundabout way. Run Oct 11, 2026 on the extract
-- idaho-261005-20261007-cd0984ee; places.json records the result and the rule each entry used.
with spec(image_id, rule, a, b, near_m, cluster_m) as (values
 (752,'cross','Chinden','Cloverdale',200,60),(753,'cross','Chinden','Five Mile',200,60),
 (754,'cross','Chinden','Maple Grove',200,60),(725,'cross','Chinden','Locust Grove',200,60),
 (655,'cross','Chinden','Eagle Road',200,60),(664,'cross','Chinden','Glenwood',200,60),
 (751,'signal','','',250,0),(835,'cross','Chinden','Tree Farm',200,60),
 (645,'cross','Chinden','Curtis|Veterans Memorial',250,90),(656,'cross','Eagle Road','Fairview',200,60),
 (657,'cross','Eagle Road','Franklin',200,60),(659,'cross','Eagle Road','Ustick',200,60),
 (658,'cross','Eagle Road','McMillan',200,60),(810,'cross','Eagle Road','St. Lukes',200,60),
 (676,'cross','I 84','Eagle Road',400,250),(698,'cross','Eagle Road','Overland',200,60),
 (674,'cross','I 84','Meridian Road',400,250),(687,'cross','I 84','I 184',700,300),
 (677,'cross','I 84','Cloverdale',400,250),(718,'cross','Meridian Road','Amity',200,60),
 (699,'cross','Overland','Locust Grove',200,60),(817,'cross','Meridian Road','Lake Hazel',200,60),
 (717,'cross','Meridian Road','Victory',200,60),(825,'cross','Meridian Road','Pine Avenue',200,60),
 (700,'cross','Meridian Road','Overland',200,60),(680,'cross','Cole','Overland',200,60),
 (737,'cross','9th Street','Idaho Street',150,40),(748,'cross','Capitol','Main Street',150,40),
 (710,'cross','Cole','Victory',200,60),(636,'cross','6th Street','Front Street',150,40),
 (792,'roundabout','','',300,0),(704,'cross','Meridian Road','Main Street',200,60),
 (709,'cross','Overland','Cloverdale',200,60),(762,'signal','','',250,0)),
cam as (select s.*, c.pole_geom g from spec s join core.camera_view v on v.image_id = s.image_id
        join core.camera c on c.id = v.camera_id),
w as (select osm_id, coalesce(name, '') || ' ' || coalesce(ref, '') label, tags, geom from core.osm_way where active),
pts as (
 select cam.image_id, (st_dump(st_intersection(wa.geom, wb.geom))).geom p
 from cam
 join w wa on cam.rule = 'cross' and wa.label ~* cam.a and st_dwithin(wa.geom::geography, cam.g::geography, cam.near_m)
 join w wb on wb.label ~* cam.b and wb.osm_id <> wa.osm_id and st_dwithin(wb.geom::geography, cam.g::geography, cam.near_m)
 where st_intersects(wa.geom, wb.geom)),
pts2 as (select pts.image_id, pts.p, st_distance(pts.p::geography, cam.g::geography) d, cam.cluster_m
         from pts join cam using (image_id) where geometrytype(pts.p) = 'POINT'),
best as (select distinct on (image_id) image_id, p p0 from pts2 order by image_id, d),
crossing as (select pts2.image_id, st_centroid(st_collect(pts2.p)) c, 'crossing of ' || count(*) || ' point(s)' how
             from pts2 join best using (image_id)
             where st_dwithin(pts2.p::geography, best.p0::geography, pts2.cluster_m) group by 1),
signal as (select distinct on (cam.image_id) cam.image_id, n.geom c, 'traffic_signals node ' || n.osm_id how
           from cam join core.osm_node n on cam.rule = 'signal' and n.active and n.kind = 'traffic_signals'
             and st_dwithin(n.geom::geography, cam.g::geography, cam.near_m)
           order by cam.image_id, st_distance(n.geom::geography, cam.g::geography)),
rb as (select distinct on (cam.image_id) cam.image_id, st_centroid(w.geom) c, 'centre of roundabout way ' || w.osm_id how
       from cam join w on cam.rule = 'roundabout' and w.tags->>'junction' = 'roundabout'
         and st_dwithin(w.geom::geography, cam.g::geography, cam.near_m)
       order by cam.image_id, st_distance(w.geom::geography, cam.g::geography)),
got as (select * from crossing union all select * from signal union all select * from rb)
select cam.image_id, round(st_x(got.c)::numeric, 6) lon, round(st_y(got.c)::numeric, 6) lat, got.how
from cam left join got using (image_id) order by cam.image_id;
