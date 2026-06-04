-- ============================================================
-- DocMind — Supabase Migration
-- Run this entire script in the Supabase SQL Editor (one shot)
-- ============================================================

-- 1. Enable pgvector extension
create extension if not exists vector;

-- 2. Documents table
create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  filename text not null unique,
  file_hash text,
  created_at timestamptz default now()
);

-- 3. Document chunks table (with 1536-dim embedding column)
create table if not exists document_chunks (
  id uuid primary key default gen_random_uuid(),
  doc_id uuid references documents(id) on delete cascade,
  content text not null,
  embedding vector(1536),
  metadata jsonb,
  created_at timestamptz default now()
);

-- 4. IVFFlat index for approximate nearest neighbor search
create index if not exists document_chunks_embedding_idx
  on document_chunks
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

-- 5. Cosine similarity search function (RPC)
create or replace function match_documents(
  query_embedding vector(1536),
  match_threshold float default 0.7,
  match_count int default 5
)
returns table (
  id uuid,
  doc_id uuid,
  content text,
  metadata jsonb,
  filename text,
  similarity float
)
language sql stable
as $$
  select
    dc.id,
    dc.doc_id,
    dc.content,
    dc.metadata,
    d.filename,
    1 - (dc.embedding <=> query_embedding) as similarity
  from document_chunks dc
  join documents d on d.id = dc.doc_id
  where 1 - (dc.embedding <=> query_embedding) > match_threshold
  order by dc.embedding <=> query_embedding
  limit match_count;
$$;

-- 6. Row Level Security
alter table documents enable row level security;
alter table document_chunks enable row level security;

-- Service role key bypasses RLS automatically.
-- Anon key gets read-only access:
create policy "anon read documents"
  on documents for select
  using (true);

create policy "anon read chunks"
  on document_chunks for select
  using (true);

-- Service role needs insert/update/delete for ingestion:
create policy "service insert documents"
  on documents for insert
  with check (true);

create policy "service delete documents"
  on documents for delete
  using (true);

create policy "service insert chunks"
  on document_chunks for insert
  with check (true);

create policy "service delete chunks"
  on document_chunks for delete
  using (true);
