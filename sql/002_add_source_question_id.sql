IF COL_LENGTH(N'dbo.search_queries', N'source_question_id') IS NULL
BEGIN
    ALTER TABLE dbo.search_queries
        ADD source_question_id nvarchar(50) NULL;
END;
