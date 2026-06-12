INSERT INTO support_devices (site_id, model, firmware_version, config_hash,
                             install_date, status, last_heartbeat, created_at)
VALUES (:site_id, :model, :firmware_version, :config_hash,
        :install_date, :status, :last_heartbeat, :created_at)
