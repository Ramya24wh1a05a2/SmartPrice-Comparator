-- SmartPrice schema (MySQL / MariaDB). Each statement ends with a semicolon.

CREATE TABLE IF NOT EXISTS users (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(100) NOT NULL,
  email         VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS products (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  search_key  VARCHAR(255) NOT NULL UNIQUE,
  name        VARCHAR(255) NOT NULL,
  brand       VARCHAR(100),
  category    VARCHAR(100),
  description TEXT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS platform_prices (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  product_id    INT NOT NULL,
  platform      VARCHAR(60) NOT NULL,
  min_price     INT NOT NULL,
  max_price     INT NOT NULL,
  typical_price INT NOT NULL,
  mrp           INT NOT NULL,
  delivery      VARCHAR(60),
  delivery_fee  VARCHAR(60),
  offer         VARCHAR(255),
  in_stock      TINYINT(1) NOT NULL DEFAULT 1,
  rating        DECIMAL(2,1),
  reviews       INT,
  direct_url    VARCHAR(1000),
  UNIQUE KEY uq_product_platform (product_id, platform),
  CONSTRAINT fk_pp_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS price_alerts (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  user_id       INT NOT NULL,
  email         VARCHAR(255) NOT NULL,
  product_name  VARCHAR(255) NOT NULL,
  search_query  VARCHAR(255) NOT NULL,
  target_price  INT NOT NULL,
  current_best  INT,
  best_platform VARCHAR(60),
  fulfilled     TINYINT(1) NOT NULL DEFAULT 0,
  notified_at   DATETIME NULL,
  set_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_alerts_user (user_id),
  INDEX idx_alerts_pending (fulfilled),
  CONSTRAINT fk_alert_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS search_history (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  user_id      INT NOT NULL,
  query        VARCHAR(255) NOT NULL,
  product_name VARCHAR(255),
  searched_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_history_user (user_id),
  CONSTRAINT fk_sh_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Real price history: one row per live price we fetch (this is what makes the charts real over time)
CREATE TABLE IF NOT EXISTS price_history (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  product_key VARCHAR(255) NOT NULL,
  platform    VARCHAR(60)  NOT NULL,
  price       INT NOT NULL,
  recorded_at DATETIME NOT NULL,
  INDEX idx_ph_lookup (product_key, platform, recorded_at)
) ENGINE=InnoDB;
