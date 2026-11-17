CREATE TABLE ai_hr_item_retry (
 tenant_id VARCHAR(64) NOT NULL,item_id CHAR(36) NOT NULL,generation INT NOT NULL,
 PRIMARY KEY(tenant_id,item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
