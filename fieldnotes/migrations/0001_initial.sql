CREATE TABLE audit (
	id VARCHAR(32) NOT NULL, 
	actor VARCHAR(64) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	target VARCHAR(80) NOT NULL, 
	created_at FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_audit_created_at ON audit (created_at);

CREATE TABLE login_buckets (
	"key" VARCHAR(100) NOT NULL, 
	count INTEGER NOT NULL, 
	expires_at FLOAT NOT NULL, 
	PRIMARY KEY ("key")
);

CREATE INDEX ix_login_buckets_expires_at ON login_buckets (expires_at);

CREATE TABLE notebooks (
	id VARCHAR(32) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	name_key VARCHAR(160) NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	version INTEGER NOT NULL, 
	created_at FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name_key)
);

CREATE TABLE users (
	id VARCHAR(32) NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	password_hash TEXT NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
);

CREATE TABLE pages (
	id VARCHAR(32) NOT NULL, 
	notebook_id VARCHAR(32) NOT NULL, 
	slug VARCHAR(100) NOT NULL, 
	version INTEGER NOT NULL, 
	current_revision INTEGER NOT NULL, 
	published_revision INTEGER, 
	archived BOOLEAN NOT NULL, 
	created_at FLOAT NOT NULL, 
	published_at FLOAT, 
	reviewed_at FLOAT, 
	review_interval_days INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(notebook_id) REFERENCES notebooks (id) ON DELETE RESTRICT, 
	UNIQUE (slug)
);

CREATE INDEX ix_pages_notebook_id ON pages (notebook_id);

CREATE TABLE sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(32) NOT NULL, 
	csrf VARCHAR(64) NOT NULL, 
	expires_at FLOAT NOT NULL, 
	PRIMARY KEY (token_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_sessions_expires_at ON sessions (expires_at);

CREATE TABLE bookmarks (
	user_id VARCHAR(32) NOT NULL, 
	page_id VARCHAR(32) NOT NULL, 
	created_at FLOAT NOT NULL, 
	PRIMARY KEY (user_id, page_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(page_id) REFERENCES pages (id) ON DELETE CASCADE
);

CREATE TABLE revisions (
	id VARCHAR(32) NOT NULL, 
	page_id VARCHAR(32) NOT NULL, 
	number INTEGER NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	summary VARCHAR(500) NOT NULL, 
	body TEXT NOT NULL, 
	tags JSON NOT NULL, 
	steps JSON NOT NULL, 
	author VARCHAR(64) NOT NULL, 
	message VARCHAR(200) NOT NULL, 
	created_at FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_page_revision UNIQUE (page_id, number), 
	FOREIGN KEY(page_id) REFERENCES pages (id) ON DELETE CASCADE
);

CREATE TABLE runs (
	id VARCHAR(32) NOT NULL, 
	page_id VARCHAR(32) NOT NULL, 
	owner_id VARCHAR(32) NOT NULL, 
	source_revision INTEGER NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	steps JSON NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	version INTEGER NOT NULL, 
	created_at FLOAT NOT NULL, 
	finished_at FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(page_id) REFERENCES pages (id) ON DELETE RESTRICT, 
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_runs_owner_id ON runs (owner_id);

CREATE INDEX ix_runs_owner_time ON runs (owner_id, created_at);

CREATE INDEX ix_runs_page_id ON runs (page_id);

CREATE TABLE "references" (
	revision_id VARCHAR(32) NOT NULL, 
	target_slug VARCHAR(100) NOT NULL, 
	PRIMARY KEY (revision_id, target_slug), 
	FOREIGN KEY(revision_id) REFERENCES revisions (id) ON DELETE CASCADE
);

CREATE INDEX ix_references_target_slug ON "references" (target_slug);

CREATE VIRTUAL TABLE revision_search USING fts5(revision_id UNINDEXED, title, summary, body, tags, tokenize='unicode61', prefix='2 3');
