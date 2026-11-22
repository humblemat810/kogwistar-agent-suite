use crate::profiles::{DeveloperPack, DeveloperProfileBuilder};
use crate::selection::SuiteSelection;

pub fn main(args: &[String]) -> i32 {
    match args.first().map(String::as_str) {
        Some("profile") => match run_profile() {
            Ok(output) => {
                println!("{output}");
                0
            }
            Err(error) => {
                eprintln!("{error}");
                1
            }
        },
        _ => {
            eprintln!("usage: kogwistar-agent-suite profile");
            1
        }
    }
}

fn run_profile() -> Result<String, crate::errors::SuiteError> {
    let pack: DeveloperPack = DeveloperProfileBuilder::new()
        .workspace_root(".")
        .selection(SuiteSelection::from_env()?)
        .build()?;
    let capabilities = vec![
        "workspace.read".to_string(),
        "git.read".to_string(),
        "shell.test".to_string(),
    ];
    let results = pack.search("", &capabilities, None, "lexical", 20)?;
    Ok(serde_json::to_string_pretty(&results)?)
}
