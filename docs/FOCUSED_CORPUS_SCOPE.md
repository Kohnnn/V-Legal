# Focused Corpus Scope

V-Legal's primary corpus is not meant to be a broad all-law archive. It is a focused research database for economy, finance, and industry-sector legal work that supports equity and sector analysis.

## Inclusion Goals

Include documents that shape:

- corporate formation, governance, shareholder rights, restructuring, and M&A
- securities, banking, credit, foreign exchange, insurance, accounting, audit, tax, fees, and pricing
- investment, procurement, trade, customs, import/export, logistics, and market operations
- real estate, land use, housing development, construction, infrastructure, and industrial zones
- energy, power, oil and gas, mining, transport, telecom, technology, healthcare, pharmaceuticals, and other commercially material sectors
- business-facing labor, employment, wages, and social-insurance rules
- provincial and municipal sector regulations when they clearly govern commercial or industry activity

## Exclusion Goals

Exclude documents whose primary subject is:

- constitutional law
- criminal law and criminal procedure
- military and national-defense administration
- police/public-security administration unless a document clearly hits a commercial override
- general civil-status matters such as marriage, family, inheritance, nationality, residence, or household registration
- general civil-service, cadre, emulation, reward, and state-apparatus administration
- general education and public-sector administration that do not directly affect commercial or sector regulation

## Issuer Rules

### Strong Include Issuers

- Bộ Tài chính
- Ngân hàng Nhà nước
- Ủy ban Chứng khoán
- Bộ Kế hoạch và Đầu tư
- Bộ Công Thương
- Bộ Xây dựng
- Bộ Tài nguyên và Môi trường
- Bộ Y tế
- Bộ Thông tin và Truyền thông
- Bộ Giao thông vận tải
- Bộ Nông nghiệp và Phát triển nông thôn

### Conditional Include Issuers

- Chính phủ
- Thủ tướng Chính phủ
- Quốc hội
- Chủ tịch nước
- UBND / Ủy ban nhân dân
- HĐND / Hội đồng nhân dân

These issuers are included when the document also carries strong economy, commercial, or sector signals in its title or sector metadata.

### Heavily Filtered Issuers

- Bộ Công an
- Bộ Giáo dục và Đào tạo
- Bộ Nội vụ
- Bộ Quốc phòng
- Bộ Tư pháp

These issuers default to excluded unless a document carries strong commercial or sector overrides.

## Metadata Signals

The focused rebuild prefers documents with one or more of these metadata signals:

- issuer matches a strong include issuer
- legal sector matches finance, banking, investment, trade, tax, customs, construction, real estate, land, environment, transport, telecom, healthcare, agriculture, or labor keywords
- title contains strong commercial or sector terms such as `doanh nghiệp`, `chứng khoán`, `ngân hàng`, `đầu tư`, `đấu thầu`, `thuế`, `hải quan`, `bất động sản`, `đất đai`, `điện lực`, `dầu khí`, `viễn thông`, or `dược`

Public-law and general-civil keywords lower a document's score and can exclude it when no commercial override is present.

## Operational Rule

The focused corpus is rebuilt from Hugging Face metadata plus cached HTML content using:

```bash
uv run python scripts/bootstrap_hf_focused_corpus.py --reset
```

This rebuild is ordered from newest to oldest so the resulting corpus favors more recent regulatory material when the source dataset is uneven.
