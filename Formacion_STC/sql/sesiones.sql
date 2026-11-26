WITH LINKS AS (
  SELECT
    E100160.CONFIG_VIRTUAL_TUTORING_RESOURCE_CLASS_SESSION_ID AS class_session_id,
    E100160.CONFIG_VIRTUAL_TUTORING_RESOURCE_STREAMING_EXTERNAL_LINK AS MEET_LINK
  FROM `potent-poetry-284019.DSS3_SIS.ES3100160_academic_resource` E100160
  WHERE CONFIG_VIRTUAL_TUTORING_RESOURCE_CLASS_SESSION_ID IS NOT NULL
),

SESIONES AS (
  SELECT 
    A.CREATED_AT, 
    A._ID AS CLASS_SESSION_ID,
    A.STRUCTURE_ID,
    B.DESCRIPTION AS PROGRAMA,
    A.NAME AS NAME_SESSION,
    FORMAT_DATE('%d/%m/%Y', A.START_DATE) AS STAR_DATE,
    A.NUMBER_SESSION,
    C.NAME AS STRUCTURE_CATEGORY
  FROM `potent-poetry-284019.DSS3_SIS.ES3100410_class_session` A
  LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100100_structure` B
    ON B._ID = A.STRUCTURE_ID
  LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100145_structure_category` C
    ON B.STRUCTURE_CATEGORY_ID = C._ID
  WHERE B.DESCRIPTION IS NOT NULL
)

SELECT 
  S.*,
  TRIM(REPLACE(L.MEET_LINK, 'https://', '')) AS MEET_LINK
FROM SESIONES S 
LEFT JOIN LINKS L
  ON S.CLASS_SESSION_ID = L.class_session_id
  WHERE (
    TRIM(REPLACE(L.MEET_LINK, 'https://', '')) NOT IN (
      'meet.google.com/puu-qsvr-nwh', 
      'meet.google.com/fjs-oggk-kor', 
      'meet.google.com/zey-hwes-prb', 
      'meet.google.com/wkz-zrcj-cit', 
      'meet.google.com/khw-kiev-toj', 
      'meet.google.com/fgc-kidi-uww'
    ) 
    OR L.MEET_LINK IS NULL
  )

  ORDER BY STRUCTURE_ID DESC, NUMBER_SESSION DESC
