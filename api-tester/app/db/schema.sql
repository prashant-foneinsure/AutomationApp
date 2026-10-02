-- AutomationAppDb schema. Idempotent: safe to re-run.
-- Conventions follow the existing SchoolManagementSystemDb: int IDENTITY keys
-- named <Entity>Id, datetime2 timestamps, bit flags.
-- All timestamps are stored in UTC via SYSUTCDATETIME().

IF OBJECT_ID('TestGroups', 'U') IS NULL
CREATE TABLE TestGroups (
    GroupId      int IDENTITY(1,1) NOT NULL CONSTRAINT PK_TestGroups PRIMARY KEY,
    Name         nvarchar(200) NOT NULL,
    Description  nvarchar(max) NULL,
    CreatedAt    datetime2 NOT NULL CONSTRAINT DF_TestGroups_CreatedAt DEFAULT SYSUTCDATETIME(),
    UpdatedAt    datetime2 NOT NULL CONSTRAINT DF_TestGroups_UpdatedAt DEFAULT SYSUTCDATETIME()
);
GO

-- Group name is the user-facing identity. Collation is
-- SQL_Latin1_General_CP1_CI_AS, so this is case-insensitive: "Event API" and
-- "event api" collide by design and the repository surfaces that as a 409.
-- Guarded on the INDEX, not the table: the table was created in the previous
-- batch, so an OBJECT_ID(...) IS NULL guard would always be false here and the
-- constraint would silently never be created.
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID('TestGroups') AND name = 'UQ_TestGroups_Name')
    ALTER TABLE TestGroups ADD CONSTRAINT UQ_TestGroups_Name UNIQUE (Name);
GO

IF OBJECT_ID('ApiTests', 'U') IS NULL
CREATE TABLE ApiTests (
    TestId      int IDENTITY(1,1) NOT NULL CONSTRAINT PK_ApiTests PRIMARY KEY,
    GroupId     int NOT NULL CONSTRAINT FK_ApiTests_TestGroups
                    REFERENCES TestGroups(GroupId) ON DELETE CASCADE,
    Name        nvarchar(200) NOT NULL,
    Curl        nvarchar(max) NOT NULL,
    HttpMethod  nvarchar(10) NULL,
    -- JSON array of {name, selector} applied after a passing baseline.
    Extractors  nvarchar(max) NULL,
    -- Execution order within the group; drives the Run Group chain.
    SortOrder   int NOT NULL CONSTRAINT DF_ApiTests_SortOrder DEFAULT 0,
    Notes       nvarchar(max) NULL,
    CreatedAt   datetime2 NOT NULL CONSTRAINT DF_ApiTests_CreatedAt DEFAULT SYSUTCDATETIME(),
    UpdatedAt   datetime2 NOT NULL CONSTRAINT DF_ApiTests_UpdatedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_ApiTests_Group_Name UNIQUE (GroupId, Name)
);
GO

-- Drives the ordered "run group" chain and the tests grid within a group.
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID('ApiTests') AND name = 'IX_ApiTests_Group_SortOrder')
    CREATE INDEX IX_ApiTests_Group_SortOrder ON ApiTests(GroupId, SortOrder, TestId);
GO

IF OBJECT_ID('TestRuns', 'U') IS NULL
CREATE TABLE TestRuns (
    RunId          bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_TestRuns PRIMARY KEY,
    TestId         int NOT NULL CONSTRAINT FK_TestRuns_ApiTests
                        REFERENCES ApiTests(TestId) ON DELETE CASCADE,
    -- 'completed' | 'aborted' -- a group run that stopped at the first failure.
    Outcome        nvarchar(20) NOT NULL CONSTRAINT DF_TestRuns_Outcome DEFAULT 'completed',
    StartedAt      datetime2 NOT NULL CONSTRAINT DF_TestRuns_StartedAt DEFAULT SYSUTCDATETIME(),
    FinishedAt     datetime2 NULL,
    BaselineStatus int NULL,
    PassedCount    int NOT NULL CONSTRAINT DF_TestRuns_Passed DEFAULT 0,
    TotalCount     int NOT NULL CONSTRAINT DF_TestRuns_Total DEFAULT 0,
    DurationMs     int NOT NULL CONSTRAINT DF_TestRuns_Duration DEFAULT 0,
    -- Present when the run came from the Run Group chain.
    GroupRunId     bigint NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID('TestRuns') AND name = 'IX_TestRuns_TestId_StartedAt')
    CREATE INDEX IX_TestRuns_TestId_StartedAt ON TestRuns(TestId, StartedAt DESC);
GO

IF OBJECT_ID('RunCases', 'U') IS NULL
CREATE TABLE RunCases (
    CaseId           bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_RunCases PRIMARY KEY,
    RunId            bigint NOT NULL CONSTRAINT FK_RunCases_TestRuns
                        REFERENCES TestRuns(RunId) ON DELETE CASCADE,
    Name             nvarchar(300) NOT NULL,
    Category         nvarchar(50) NOT NULL,
    Method           nvarchar(10) NULL,
    Body             nvarchar(max) NULL,
    RemoveHeaders    nvarchar(max) NULL,
    ExpectedStatus   int NULL,
    ActualStatus     int NULL,
    TimeMs           int NOT NULL CONSTRAINT DF_RunCases_Time DEFAULT 0,
    Passed           bit NOT NULL CONSTRAINT DF_RunCases_Passed DEFAULT 0,
    RequestJson      nvarchar(max) NULL,
    ResponseHeaders  nvarchar(max) NULL,
    ResponseBody     nvarchar(max) NULL,
    -- 'baseline' for the original valid request, 'generated' for LLM cases,
    -- 'auth' for the missing-credentials case.
    Origin           nvarchar(20) NOT NULL CONSTRAINT DF_RunCases_Origin DEFAULT 'generated'
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID('RunCases') AND name = 'IX_RunCases_RunId')
    CREATE INDEX IX_RunCases_RunId ON RunCases(RunId);
GO

-- Learning loop. One row per human verdict on a generated case; the prompt
-- builder replays accepted cases as few-shot examples and rejected ones as
-- negative guidance.
IF OBJECT_ID('CaseFeedback', 'U') IS NULL
CREATE TABLE CaseFeedback (
    FeedbackId  bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_CaseFeedback PRIMARY KEY,
    CaseId      bigint NOT NULL CONSTRAINT FK_CaseFeedback_RunCases
                    REFERENCES RunCases(CaseId) ON DELETE CASCADE,
    TestId      int NOT NULL,
    -- 'accepted' | 'rejected' | 'edited'
    Verdict     nvarchar(20) NOT NULL,
    Note        nvarchar(max) NULL,
    CreatedAt   datetime2 NOT NULL CONSTRAINT DF_CaseFeedback_CreatedAt DEFAULT SYSUTCDATETIME()
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID('CaseFeedback') AND name = 'IX_CaseFeedback_TestId')
    CREATE INDEX IX_CaseFeedback_TestId ON CaseFeedback(TestId, Verdict);
GO

-- Values captured from a passing run (e.g. a bearer token) and substituted
-- into {{placeholders}} by later tests in the same group.
IF OBJECT_ID('GroupVariables', 'U') IS NULL
CREATE TABLE GroupVariables (
    GroupId       int NOT NULL CONSTRAINT FK_GroupVariables_TestGroups
                      REFERENCES TestGroups(GroupId) ON DELETE CASCADE,
    Name          nvarchar(200) NOT NULL,
    Value         nvarchar(max) NULL,
    -- Full JSON fragment, so nested values can be re-extracted from.
    JsonValue     nvarchar(max) NULL,
    SourceTestId  int NULL,
    SourceRunId   bigint NULL,
    UpdatedAt     datetime2 NOT NULL CONSTRAINT DF_GroupVariables_UpdatedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_GroupVariables PRIMARY KEY (GroupId, Name)
);
GO
