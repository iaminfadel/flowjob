import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.resume_parser import parse_master_resume

def validate_resume(path: str = "master_resume.md") -> bool:
    """Validate the master resume and print diagnostics."""
    try:
        metadata, content = parse_master_resume(path)
        print("✅ Master resume YAML schema is valid.")
        print(f"   Schema version: {metadata.schema_version}")
        num_skills = sum(len(v) for v in metadata.skills.values())
        print(f"   Skills mapped: {num_skills}")
        
        # Check for bracket tags in markdown body
        if "[" not in content or "]" not in content:
            print("⚠️ Warning: No [bracket] tags found in markdown body.")
        else:
            print("✅ Markdown body contains bracket tags.")
            
        return True
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False

if __name__ == "__main__":
    validate_resume()
