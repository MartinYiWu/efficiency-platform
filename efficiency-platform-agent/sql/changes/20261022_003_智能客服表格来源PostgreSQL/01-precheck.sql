SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'customer_service' AND table_name = 'document_parent'
ORDER BY ordinal_position;
