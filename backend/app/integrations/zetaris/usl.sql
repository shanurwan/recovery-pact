-- RecoveryPact's business model as a Zetaris Unified Semantic Layer: recovery_business.
-- Run by `python -m app.integrations.zetaris.setup --usl` after the base sources exist.
-- Statements are separated by a line holding only ";;". {CONT}, {SHOP} and {CAL} are the
-- datasource / Lightning database names from settings.
--
-- The data-quality rules are not hygiene: they are policy inputs. A workload whose registry
-- row fails a rule is treated as UNKNOWN by the Continuity Guardian (invariant I4: no kill),
-- because a registry that contradicts itself can't vouch for a kill.

CREATE NAMESPACE IF NOT EXISTS lightning.metastore
;;
CREATE NAMESPACE IF NOT EXISTS lightning.metastore.recoverypact
;;
COMPILE USL IF NOT EXISTS recovery_business DEPLOY NAMESPACE lightning.metastore.recoverypact DDL
CREATE TABLE owner (
    owner_team varchar(60) NOT NULL PRIMARY KEY,
    oncall varchar(80) NOT NULL,
    channel varchar(80) NOT NULL
);
CREATE TABLE workload (
    application_name varchar(80) NOT NULL PRIMARY KEY,
    job_name varchar(80) NOT NULL,
    owner_team varchar(60) NOT NULL FOREIGN KEY REFERENCES owner(owner_team),
    workload_class varchar(40) NOT NULL,
    replayable boolean,
    replay_cost_minutes int,
    typical_runtime_s int,
    interrupt_policy varchar(40) NOT NULL,
    business_purpose varchar(400)
);
CREATE TABLE change_window (
    change_id varchar(40) NOT NULL PRIMARY KEY,
    scope_type varchar(20) NOT NULL,
    scope varchar(80) NOT NULL,
    window_start varchar(30) NOT NULL,
    window_end varchar(30) NOT NULL,
    policy varchar(40) NOT NULL,
    reason varchar(400)
);
CREATE TABLE service_slo (
    service varchar(40) NOT NULL PRIMARY KEY,
    slo_success_rate decimal(5,4) NOT NULL,
    slo_p95_ms int NOT NULL,
    verification_window_s int NOT NULL,
    revenue_per_minute_cents int NOT NULL,
    max_degradation_s int NOT NULL,
    tier varchar(20) NOT NULL
);
;;
ACTIVATE USL TABLE lightning.metastore.recoverypact.recovery_business.owner AS
SELECT owner_team, oncall, channel FROM {CONT}.escalation_contacts
;;
ACTIVATE USL TABLE lightning.metastore.recoverypact.recovery_business.workload AS
SELECT application_name, job_name, owner_team, workload_class, replayable, replay_cost_minutes,
       typical_runtime_s, interrupt_policy, business_purpose
FROM {CONT}.workload_registry
;;
ACTIVATE USL TABLE lightning.metastore.recoverypact.recovery_business.change_window AS
SELECT COALESCE(change_id, '') AS change_id, COALESCE(scope_type, '') AS scope_type, COALESCE(scope, '') AS scope,
       COALESCE(window_start, '') AS window_start, COALESCE(window_end, '') AS window_end,
       COALESCE(policy, '') AS policy, reason
FROM {CAL}.change_calendar
;;
ACTIVATE USL TABLE lightning.metastore.recoverypact.recovery_business.service_slo AS
SELECT service, slo_success_rate, slo_p95_ms, verification_window_s, revenue_per_minute_cents,
       max_degradation_s, tier
FROM {CONT}.service_slo
;;
UPDATE USL lightning.metastore.recoverypact.recovery_business SET DESCRIPTION "What the business knows about every workload that can hold a lock on checkout: who owns it, whether it may be stopped, what restarting it costs, when it is frozen, and what recovered means."
;;
UPDATE USL lightning.metastore.recoverypact.recovery_business.workload SET TABLE DESCRIPTION "System of record for database workloads. interrupt_policy is the owner's ruling; a kill is only ever considered for may_interrupt work that is replayable at a known cost."
;;
UPDATE USL lightning.metastore.recoverypact.recovery_business.owner SET TABLE DESCRIPTION "Owning team and on-call route for each workload; where an escalation goes."
;;
UPDATE USL lightning.metastore.recoverypact.recovery_business.change_window SET TABLE DESCRIPTION "Change-management windows from the change calendar. consult_owner means the owner decides, whatever the registry says."
;;
UPDATE USL lightning.metastore.recoverypact.recovery_business.service_slo SET TABLE DESCRIPTION "What the business is back means for each customer-facing service, and how long it tolerates degradation."
;;
REGISTER DQ policy_known TABLE lightning.metastore.recoverypact.recovery_business.workload AS interrupt_policy IN ('may_interrupt', 'never_interrupt')
;;
REGISTER DQ interruptible_is_replayable TABLE lightning.metastore.recoverypact.recovery_business.workload AS interrupt_policy <> 'may_interrupt' OR (replayable = true AND replay_cost_minutes IS NOT NULL AND replay_cost_minutes >= 0)
;;
REGISTER DQ protected_never_interrupted TABLE lightning.metastore.recoverypact.recovery_business.workload AS workload_class <> 'PROTECTED_SETTLEMENT' OR interrupt_policy = 'never_interrupt'
;;
REGISTER DQ window_ordered TABLE lightning.metastore.recoverypact.recovery_business.change_window AS window_end > window_start
;;
REGISTER DQ slo_sane TABLE lightning.metastore.recoverypact.recovery_business.service_slo AS slo_success_rate > 0 AND slo_success_rate <= 1 AND max_degradation_s >= 0 AND revenue_per_minute_cents >= 0
