-- Применить к СУЩЕСТВУЮЩЕЙ БД один раз (команда повторного запуска безопасна).
-- Никаких новых счетов/транзакций; только метаданные скоринга.
BEGIN;
INSERT INTO alfa.scoring_rules (rule_version, parameters, description)
VALUES (
  'rules-v2-bank',
  '{"base_weight":0.85,"bank_weight":0.15,"history_months":3,"sales_categories":["SALES"],"expense_categories":["OPERATING"],"low_min":75,"medium_min":50}'::jsonb,
  'Демонстрационная оценка с подтверждёнными банковскими поступлениями (НЕ банковская модель для реального кредитования)'
)
ON CONFLICT (rule_version) DO NOTHING;

INSERT INTO alfa.reason_codes(code, client_message) VALUES
('BANK_TURNOVER_MISMATCH', 'Поступления по счёту расходятся с выручкой, указанной в анкете.'),
('BANK_TURNOVER_UNSTABLE', 'Поступления по счетам компании нестабильны.'),
('BANK_HISTORY_INCOMPLETE', 'Нет подтверждённой банковской истории за три полных месяца.')
ON CONFLICT (code) DO NOTHING;
COMMIT;
