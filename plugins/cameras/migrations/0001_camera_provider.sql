-- cameras/0001: who runs each camera, so road-weather stations can live beside ACHD's
-- traffic cameras (docs/14 §14.6 "Road weather", WP16; the number 0008 that §14.8
-- reserved for this, written as a plugin migration since docs/15 §15.2).
--
-- core.camera holds ACHD's traffic cameras (achd_cameras) and, from WP16, ITD's
-- road-weather (RWIS) stations statewide and Oregon DOT cameras in the regional ring
-- (idaho511_rwis_sites_oneoff). Each station is one camera; each of its views (one per
-- direction, 2 to 4 at a station) is a core.camera_view with its 511 image id. A view's
-- direction label goes in core.camera_view.direction, which already exists ("coarse
-- facing, if the source gives one"), so camera_view needs nothing new.
--
-- The Cameras layer shows provider 'ACHD' only; the Road weather layer shows the rest.

alter table core.camera add column provider text not null default 'ACHD'
  check (provider in ('ACHD', 'ITD RWIS', 'ODOT'));

comment on column core.camera.provider is
  'Who runs the camera: ACHD (traffic cameras), ITD RWIS (road-weather stations) or ODOT (Oregon DOT, regional ring)';
