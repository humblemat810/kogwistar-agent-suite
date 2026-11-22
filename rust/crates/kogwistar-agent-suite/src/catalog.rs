use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::authorization::AclResolver;
use crate::errors::{SuiteError, SuiteResult};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum CapabilityKind {
    Tool,
    Mcp,
    Skill,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CapabilityDescriptor {
    pub capability_id: String,
    pub name: String,
    pub kind: CapabilityKind,
    pub summary: String,
    #[serde(default)]
    pub required_capabilities: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default = "default_provider")]
    pub provider_id: String,
    #[serde(default)]
    pub semantic_ready: bool,
    #[serde(default)]
    pub metadata: BTreeMap<String, String>,
}

fn default_provider() -> String {
    "kogwistar-agent-suite".into()
}

impl CapabilityDescriptor {
    pub fn searchable_text(&self) -> String {
        let metadata = self
            .metadata
            .iter()
            .map(|(key, value)| format!("{key} {value}"))
            .collect::<Vec<_>>()
            .join(" ");
        format!(
            "{} {} {} {} {}",
            self.capability_id,
            self.name,
            self.summary,
            self.tags.join(" "),
            metadata
        )
        .to_lowercase()
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CapabilitySearchResult {
    pub descriptor: CapabilityDescriptor,
    pub score: f64,
    pub r#match: String,
}

pub trait SemanticRanker: Send + Sync {
    fn rank(&self, query: &str, candidates: &[CapabilityDescriptor]) -> BTreeMap<String, f64>;
}

#[derive(Default)]
pub struct CapabilityCatalog {
    items: BTreeMap<String, CapabilityDescriptor>,
    pub semantic_ranker: Option<Box<dyn SemanticRanker>>,
}

fn tokens(value: &str) -> Vec<String> {
    static TOKEN: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let token = TOKEN.get_or_init(|| regex::Regex::new(r"[A-Za-z0-9_]+").unwrap());
    token
        .find_iter(value)
        .map(|part| part.as_str().to_lowercase())
        .collect()
}

impl CapabilityCatalog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn from_items(items: impl IntoIterator<Item = CapabilityDescriptor>) -> SuiteResult<Self> {
        let mut catalog = Self::new();
        for item in items {
            catalog.add(item)?;
        }
        Ok(catalog)
    }

    pub fn add(&mut self, descriptor: CapabilityDescriptor) -> SuiteResult<()> {
        if self
            .items
            .insert(descriptor.capability_id.clone(), descriptor)
            .is_some()
        {
            return Err(SuiteError::Duplicate {
                kind: "capability",
                id: "duplicate".into(),
            });
        }
        Ok(())
    }

    pub fn set_semantic_ready(&mut self, capability_id: &str, ready: bool) -> SuiteResult<()> {
        let item = self
            .items
            .get_mut(capability_id)
            .ok_or_else(|| SuiteError::Unknown {
                kind: "capability",
                id: capability_id.into(),
            })?;
        item.semantic_ready = ready;
        Ok(())
    }

    pub fn search(
        &self,
        query: &str,
        allowed_capabilities: &[String],
        acl: Option<&AclResolver<'_>>,
        mode: &str,
        limit: usize,
    ) -> SuiteResult<Vec<CapabilityDescriptor>> {
        Ok(self
            .search_ranked(query, allowed_capabilities, acl, mode, limit)?
            .into_iter()
            .map(|result| result.descriptor)
            .collect())
    }

    pub fn search_ranked(
        &self,
        query: &str,
        allowed_capabilities: &[String],
        acl: Option<&AclResolver<'_>>,
        mode: &str,
        limit: usize,
    ) -> SuiteResult<Vec<CapabilitySearchResult>> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        if !matches!(mode, "lexical" | "bm25" | "semantic") {
            return Err(SuiteError::Invalid(
                "mode must be lexical, bm25, or semantic".into(),
            ));
        }
        let query = query.trim().to_lowercase();
        let visible: Vec<&CapabilityDescriptor> = self
            .items
            .values()
            .filter(|item| {
                item.required_capabilities
                    .iter()
                    .all(|capability| allowed_capabilities.contains(capability))
                    && acl.is_none_or(|acl| acl(item))
            })
            .collect();
        if query.is_empty() {
            return Ok(visible
                .iter()
                .take(limit)
                .map(|item| CapabilitySearchResult {
                    descriptor: (*item).clone(),
                    score: 1.0,
                    r#match: "lexical".into(),
                })
                .collect());
        }

        if mode == "semantic" {
            let Some(ranker) = &self.semantic_ranker else {
                return Err(SuiteError::Invalid(
                    "semantic ranker is not configured".into(),
                ));
            };
            let candidates: Vec<CapabilityDescriptor> = visible
                .iter()
                .filter(|item| item.semantic_ready)
                .map(|item| (*item).clone())
                .collect();
            let mut semantic: Vec<CapabilitySearchResult> = ranker
                .rank(&query, &candidates)
                .into_iter()
                .filter_map(|(id, score)| {
                    let item = candidates.iter().find(|item| item.capability_id == id)?;
                    (score.is_finite() && score > 0.0).then(|| CapabilitySearchResult {
                        descriptor: item.clone(),
                        score,
                        r#match: "semantic".into(),
                    })
                })
                .collect();
            if !semantic.is_empty() {
                semantic.sort_by(|left, right| {
                    right
                        .score
                        .partial_cmp(&left.score)
                        .unwrap_or(std::cmp::Ordering::Equal)
                        .then_with(|| {
                            left.descriptor
                                .capability_id
                                .cmp(&right.descriptor.capability_id)
                        })
                });
                semantic.truncate(limit);
                return Ok(semantic);
            }
        }

        let effective_mode = if mode == "semantic" { "bm25" } else { mode };
        let query_tokens: std::collections::BTreeSet<String> = tokens(&query).into_iter().collect();
        let token_sets: BTreeMap<&str, std::collections::BTreeSet<String>> = visible
            .iter()
            .map(|item| {
                (
                    item.capability_id.as_str(),
                    tokens(&item.searchable_text()).into_iter().collect(),
                )
            })
            .collect();
        let mut document_frequency: BTreeMap<&str, usize> = BTreeMap::new();
        for set in token_sets.values() {
            for token in set {
                *document_frequency.entry(token).or_default() += 1;
            }
        }
        let average_length = if visible.is_empty() {
            1.0
        } else {
            token_sets.values().map(|set| set.len() as f64).sum::<f64>() / visible.len() as f64
        };
        let mut ranked = Vec::new();
        for item in &visible {
            let searchable = item.searchable_text();
            let names = [
                item.capability_id.to_lowercase(),
                item.name.to_lowercase(),
                item.tags
                    .iter()
                    .map(|tag| tag.to_lowercase())
                    .collect::<Vec<_>>()
                    .join(" "),
            ];
            if names.iter().any(|name| name.contains(&query)) {
                ranked.push(CapabilitySearchResult {
                    descriptor: (*item).clone(),
                    score: 1.0,
                    r#match: "exact".into(),
                });
                continue;
            }
            if names.iter().any(|name| name.starts_with(&query)) {
                ranked.push(CapabilitySearchResult {
                    descriptor: (*item).clone(),
                    score: 0.8,
                    r#match: "prefix".into(),
                });
                continue;
            }
            let item_tokens = &token_sets[item.capability_id.as_str()];
            let overlap: Vec<&String> = item_tokens.intersection(&query_tokens).collect();
            if !overlap.is_empty() {
                let score = if effective_mode == "bm25" {
                    let document_length = item_tokens.len().max(1) as f64;
                    query_tokens
                        .iter()
                        .filter(|term| item_tokens.contains(*term))
                        .map(|term| {
                            let count = document_frequency
                                .get(term.as_str())
                                .copied()
                                .unwrap_or_default() as f64;
                            let idf =
                                (1.0 + (visible.len() as f64 - count + 0.5) / (count + 0.5)).ln();
                            let normalization =
                                1.2 * (0.25 + 0.75 * document_length / average_length.max(1.0));
                            idf * (2.2 / (1.0 + normalization))
                        })
                        .sum()
                } else {
                    0.5 + overlap.len() as f64 / query_tokens.len().max(1) as f64 / 10.0
                };
                ranked.push(CapabilitySearchResult {
                    descriptor: (*item).clone(),
                    score,
                    r#match: effective_mode.into(),
                });
                continue;
            }
            if searchable.contains(&query) {
                ranked.push(CapabilitySearchResult {
                    descriptor: (*item).clone(),
                    score: 0.3,
                    r#match: "partial".into(),
                });
            }
        }
        ranked.sort_by(|left, right| {
            right
                .score
                .partial_cmp(&left.score)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| {
                    left.descriptor
                        .capability_id
                        .cmp(&right.descriptor.capability_id)
                })
        });
        ranked.truncate(limit);
        Ok(ranked)
    }

    pub fn get(&self, capability_id: &str) -> SuiteResult<&CapabilityDescriptor> {
        self.items
            .get(capability_id)
            .ok_or_else(|| SuiteError::Unknown {
                kind: "capability",
                id: capability_id.into(),
            })
    }

    pub fn descriptors(&self) -> Vec<CapabilityDescriptor> {
        self.items.values().cloned().collect()
    }

    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }
}
