import os
import logging
import requests
import yaml
from typing import List, Optional

from src.models import FileDiff

logger = logging.getLogger(__name__)

def get_previous_commit_sha(owner: str, repo: str) -> Optional[str]:
    """
    last_commit_sha_{owner}_{repo}.txt から前回実行時のコミットSHAを読み込む。
    """
    file_path = f'last_commit_sha_{owner}_{repo}.txt'
    if not os.path.exists(file_path):
        logger.warning(f"{file_path} not found. This might be the first run.")
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        sha = f.read().strip()
        if not sha:
            logger.warning(f"{file_path} is empty.")
            return None
        return sha

def get_latest_commit_sha(owner: str, repo: str, token: str, branch: str = 'main') -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    logger.info(f"Fetching latest commit SHA from {url}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get('sha')
    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub API request failed: {e}")
        if e.response is not None:
            logger.error(f"Response body: {e.response.text}")
        raise ValueError(f"Failed to fetch latest commit sha: {e}")

def fetch_all_files_as_added(owner: str, repo: str, head_sha: str, token: str) -> List[FileDiff]:
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{head_sha}?recursive=1"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    logger.info(f"Performing full sync: fetching all files from tree {head_sha}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub API request failed: {e}")
        if e.response is not None:
            logger.error(f"Response body: {e.response.text}")
        raise ValueError(f"Failed to fetch tree: {e}")
        
    tree = response.json().get('tree', [])
    
    diffs = []
    for item in tree:
        if item.get('type') == 'blob':
            filename = item.get('path')
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{head_sha}/{filename}"
            diffs.append(FileDiff(
                filename=filename,
                previous_filename=None,
                status='added',
                raw_content_url=raw_url,
                commit_sha=head_sha
            ))
            
    return diffs

def fetch_commit_diffs(base_sha: str, head_sha: str, owner: str, repo: str, token: str) -> List[FileDiff]:
    """
    GitHub Compare APIを呼び出し、差分ファイルをFileDiffのリストとして返す。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/compare/{base_sha}...{head_sha}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    logger.info(f"Fetching commit diffs from {url}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub API request failed: {e}")
        if e.response is not None:
            logger.error(f"Response body: {e.response.text}")
        raise ValueError(f"Failed to fetch commit diffs: {e}")

    data = response.json()
    files = data.get('files', [])
    
    diffs = []
    for f in files:
        status = f.get('status')
        if status not in ['added', 'modified', 'removed', 'renamed']:
            logger.warning(f"Unexpected status '{status}' for file {f.get('filename')}. Treating as modified.")
            status = 'modified'
            
        diffs.append(FileDiff(
            filename=f.get('filename', ''),
            previous_filename=f.get('previous_filename'),
            status=status,
            raw_content_url=f.get('raw_url'),
            commit_sha=head_sha
        ))
        
    return diffs

def analyze_folder_rename(diffs: List[FileDiff], repository: str, config_path: str = 'config.yaml') -> None:
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"Config file not found for rename analysis: {config_path}")
        return
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse config file for rename analysis: {e}")
        return

    sync_targets = config.get('sync_targets', [])
    target = next((t for t in sync_targets if t.get('repository') == repository), None)
    if not target:
        logger.warning(f"Repository {repository} not found in config.")
        return

    watch_folders = target.get('watch_folders', [])
    config_updated = False

    for folder_info in watch_folders:
        watch_folder = folder_info.get('source_path')
        if not watch_folder:
            continue

        watch_prefix = watch_folder if watch_folder.endswith('/') else f"{watch_folder}/"

        files_originally_in_watch = [
            d for d in diffs 
            if (d.previous_filename and d.previous_filename.startswith(watch_prefix)) 
            or (d.filename.startswith(watch_prefix) and d.status != 'renamed')
        ]
        
        if not files_originally_in_watch:
            continue

        renamed_from_watch = [
            d for d in diffs 
            if d.status == 'renamed' and d.previous_filename and d.previous_filename.startswith(watch_prefix)
        ]
        
        ratio = len(renamed_from_watch) / len(files_originally_in_watch)
        if ratio >= 0.8 and len(renamed_from_watch) > 0:
            from collections import Counter
            new_folders = []
            for d in renamed_from_watch:
                rel_path = d.previous_filename[len(watch_prefix):]
                if d.filename.endswith(rel_path):
                    new_prefix = d.filename[:-len(rel_path)]
                    new_prefix = new_prefix.rstrip('/')
                    new_folders.append(new_prefix)
                else:
                    new_folders.append(os.path.dirname(d.filename))
                    
            most_common_new_folder = Counter(new_folders).most_common(1)[0][0]
            
            logger.warning(f"Detected folder rename from {watch_folder} to {most_common_new_folder} (Ratio: {ratio:.2f}). Auto-healing config.")
            
            folder_info['source_path'] = most_common_new_folder
            config_updated = True

    if config_updated:
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
            logger.info("config.yaml has been successfully auto-healed.")
        except Exception as e:
            logger.error(f"Failed to auto-heal config.yaml: {e}")
            raise

def validate_failsafe(diffs: List[FileDiff], watch_folder: str) -> bool:
    watch_prefix = watch_folder if watch_folder.endswith('/') else f"{watch_folder}/"
    
    relevant_diffs = [
        d for d in diffs 
        if d.filename.startswith(watch_prefix) or (d.previous_filename and d.previous_filename.startswith(watch_prefix))
    ]
    
    if not relevant_diffs:
        return True
        
    all_removed = all(d.status == 'removed' for d in relevant_diffs)
    
    if all_removed and len(relevant_diffs) > 0:
        logger.error(f"Failsafe triggered: All {len(relevant_diffs)} relevant files in '{watch_folder}' are marked as 'removed'. Aborting to prevent destructive deletion.")
        raise ValueError(f"Failsafe triggered: All files in '{watch_folder}' removed.")
        
    return True
