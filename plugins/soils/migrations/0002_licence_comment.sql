-- Corrects the licence wording in migration 0001's header, which is applied and so can't change. It said photo_stats
-- adds only NAIP's licence (public domain, credit USDA NAIP). It adds more: the palette is measured through mask v0
-- (OpenStreetMap, Overture), farm's crop cover and fields (CSB, CDL, Sentinel-2) and Sentinel-2's July median, NDVI
-- curves and colour gains, and a photo build carries every input of each export layer it reads, whole. So the
-- palette's licence is the share-alike one, ODbL-1.0, and it credits all of them (plugins/soils/README.md, "The
-- palette"). Each soils.build row records its own licence, republish and credit.
comment on table soils.build is
  'One load or photo-statistics run and the licence of what it wrote. A photo build (the palette) is ODbL-1.0: it carries every input of the export layers it reads. Load builds (SSURGO) are public domain.';
