CREATE TABLE IF NOT EXISTS ai_github.user_favorites (
  id INT AUTO_INCREMENT PRIMARY KEY,
  repo_id INT NOT NULL UNIQUE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_user_favorites_repo
    FOREIGN KEY (repo_id) REFERENCES ai_github.repos(id)
    ON DELETE CASCADE
);
