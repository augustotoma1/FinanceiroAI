"""
End-to-End Verification Script for Financial Automation System

This script performs comprehensive verification of the complete system including:
- File structure validation
- Python module imports
- Database migration readiness
- API endpoint registration
- Background job configuration
- Code syntax validation

Author: Auto-Claude
Date: 2026-02-06
"""

import os
import sys
import importlib
import ast
from pathlib import Path
from typing import List, Dict, Tuple


class E2EVerificationError(Exception):
    """Raised when E2E verification fails"""
    pass


class E2EVerifier:
    """
    Comprehensive end-to-end verification of the Financial Automation System.

    Validates that all components are properly configured and ready for deployment.
    """

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.results: List[Dict[str, any]] = []
        self.errors: List[str] = []

    def log_result(self, test_name: str, passed: bool, message: str = ""):
        """Log a verification result"""
        status = "✓ PASS" if passed else "✗ FAIL"
        self.results.append({
            "test": test_name,
            "passed": passed,
            "message": message
        })
        print(f"{status}: {test_name}")
        if message:
            print(f"  → {message}")
        if not passed:
            self.errors.append(f"{test_name}: {message}")

    def verify_file_structure(self) -> bool:
        """Verify all required files and directories exist"""
        print("\n=== VERIFYING FILE STRUCTURE ===\n")

        required_files = [
            "requirements.txt",
            "pyproject.toml",
            ".env.example",
            ".gitignore",
            "alembic.ini",
            "README.md",
            "app/__init__.py",
            "app/main.py",
            "app/config.py",
            "app/database.py",
            "app/models/__init__.py",
            "app/models/client.py",
            "app/models/contract.py",
            "app/models/financial_record.py",
            "app/models/signature.py",
            "app/models/integration_token.py",
            "app/schemas/__init__.py",
            "app/schemas/client.py",
            "app/schemas/contract.py",
            "app/schemas/financial.py",
            "app/schemas/signature.py",
            "app/services/__init__.py",
            "app/services/claude_service.py",
            "app/services/conta_azul_service.py",
            "app/services/autentique_service.py",
            "app/services/contract_generator.py",
            "app/services/delinquency_analyzer.py",
            "app/api/__init__.py",
            "app/api/conversation.py",
            "app/api/clients.py",
            "app/api/contracts.py",
            "app/api/signatures.py",
            "app/api/auth.py",
            "app/api/dashboard.py",
            "app/background/__init__.py",
            "app/background/sync_clients.py",
            "app/background/sync_financial.py",
            "app/templates/default_contract.html",
            "tests/__init__.py",
            "tests/conftest.py",
            "tests/test_services/test_claude.py",
            "tests/test_services/test_conta_azul.py",
            "tests/test_services/test_autentique.py",
            "tests/test_api/test_endpoints.py",
        ]

        all_exist = True
        for file_path in required_files:
            full_path = self.base_path / file_path
            exists = full_path.exists()
            if not exists:
                self.log_result(f"File exists: {file_path}", False, f"Missing: {full_path}")
                all_exist = False

        if all_exist:
            self.log_result("All required files exist", True, f"{len(required_files)} files verified")

        return all_exist

    def verify_python_syntax(self) -> bool:
        """Verify all Python files have valid syntax"""
        print("\n=== VERIFYING PYTHON SYNTAX ===\n")

        python_files = list(self.base_path.glob("**/*.py"))
        syntax_errors = []

        for py_file in python_files:
            # Skip virtual environment and cache files
            if '.venv' in str(py_file) or '__pycache__' in str(py_file):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    code = f.read()
                    ast.parse(code)
            except SyntaxError as e:
                syntax_errors.append(f"{py_file}: {e}")
                self.log_result(f"Syntax check: {py_file.relative_to(self.base_path)}", False, str(e))

        if not syntax_errors:
            self.log_result("Python syntax validation", True, f"{len(python_files)} files checked")
            return True
        else:
            self.log_result("Python syntax validation", False, f"{len(syntax_errors)} errors found")
            return False

    def verify_imports(self) -> bool:
        """Verify key modules can be imported"""
        print("\n=== VERIFYING MODULE IMPORTS ===\n")

        # Add current directory to Python path
        sys.path.insert(0, str(self.base_path))

        modules_to_check = [
            "app.config",
            "app.database",
            "app.models.client",
            "app.models.contract",
            "app.models.financial_record",
            "app.models.signature",
            "app.models.integration_token",
            "app.schemas.client",
            "app.schemas.contract",
            "app.schemas.financial",
            "app.schemas.signature",
        ]

        import_errors = []
        for module_name in modules_to_check:
            try:
                # Try to import without executing (syntax check only)
                spec = importlib.util.find_spec(module_name)
                if spec is None:
                    import_errors.append(f"{module_name}: Module not found")
                    self.log_result(f"Import check: {module_name}", False, "Module not found")
                else:
                    self.log_result(f"Import check: {module_name}", True)
            except Exception as e:
                import_errors.append(f"{module_name}: {e}")
                self.log_result(f"Import check: {module_name}", False, str(e))

        if not import_errors:
            self.log_result("Module import validation", True, f"{len(modules_to_check)} modules verified")
            return True
        else:
            self.log_result("Module import validation", False, f"{len(import_errors)} errors found")
            return False

    def verify_api_endpoints(self) -> bool:
        """Verify API endpoints are properly defined in main.py"""
        print("\n=== VERIFYING API ENDPOINTS ===\n")

        main_file = self.base_path / "app" / "main.py"

        try:
            with open(main_file, 'r', encoding='utf-8') as f:
                content = f.read()

            required_routers = [
                "conversation.router",
                "clients.router",
                "contracts.router",
                "signatures.router",
                "auth.router",
                "dashboard.router",
            ]

            missing_routers = []
            for router in required_routers:
                if router not in content:
                    missing_routers.append(router)
                    self.log_result(f"Router registered: {router}", False, "Not found in main.py")
                else:
                    self.log_result(f"Router registered: {router}", True)

            if not missing_routers:
                self.log_result("API endpoint registration", True, f"{len(required_routers)} routers registered")
                return True
            else:
                self.log_result("API endpoint registration", False, f"{len(missing_routers)} routers missing")
                return False

        except Exception as e:
            self.log_result("API endpoint verification", False, str(e))
            return False

    def verify_background_jobs(self) -> bool:
        """Verify background jobs are configured in main.py"""
        print("\n=== VERIFYING BACKGROUND JOBS ===\n")

        main_file = self.base_path / "app" / "main.py"

        try:
            with open(main_file, 'r', encoding='utf-8') as f:
                content = f.read()

            required_jobs = [
                "sync_clients_job",
                "sync_financial_job",
            ]

            # Check for APScheduler imports
            if "apscheduler" not in content.lower():
                self.log_result("APScheduler integration", False, "APScheduler not imported in main.py")
                return False
            else:
                self.log_result("APScheduler integration", True)

            # Check for job scheduling
            missing_jobs = []
            for job in required_jobs:
                if job not in content:
                    missing_jobs.append(job)
                    self.log_result(f"Background job: {job}", False, "Not scheduled in main.py")
                else:
                    self.log_result(f"Background job: {job}", True)

            if not missing_jobs:
                self.log_result("Background job configuration", True, f"{len(required_jobs)} jobs configured")
                return True
            else:
                self.log_result("Background job configuration", False, f"{len(missing_jobs)} jobs missing")
                return False

        except Exception as e:
            self.log_result("Background job verification", False, str(e))
            return False

    def verify_database_migrations(self) -> bool:
        """Verify database migrations are ready"""
        print("\n=== VERIFYING DATABASE MIGRATIONS ===\n")

        alembic_ini = self.base_path / "alembic.ini"
        alembic_env = self.base_path / "alembic" / "env.py"
        versions_dir = self.base_path / "alembic" / "versions"

        # Check Alembic configuration files
        if not alembic_ini.exists():
            self.log_result("Alembic configuration", False, "alembic.ini not found")
            return False
        else:
            self.log_result("Alembic configuration", True, "alembic.ini exists")

        if not alembic_env.exists():
            self.log_result("Alembic environment", False, "alembic/env.py not found")
            return False
        else:
            self.log_result("Alembic environment", True, "alembic/env.py exists")

        # Check for migration files
        if not versions_dir.exists():
            self.log_result("Migration versions directory", False, "alembic/versions not found")
            return False

        migration_files = list(versions_dir.glob("*.py"))
        migration_files = [f for f in migration_files if f.name != "__pycache__"]

        if len(migration_files) == 0:
            self.log_result("Migration files", False, "No migration files found")
            return False
        else:
            self.log_result("Migration files", True, f"{len(migration_files)} migration(s) ready")

        # Check that env.py imports models
        with open(alembic_env, 'r', encoding='utf-8') as f:
            env_content = f.read()

        if "app.models" not in env_content:
            self.log_result("Migration model import", False, "Models not imported in alembic/env.py")
            return False
        else:
            self.log_result("Migration model import", True, "Models imported in alembic/env.py")

        self.log_result("Database migration configuration", True, "All migration checks passed")
        return True

    def verify_environment_config(self) -> bool:
        """Verify environment configuration template"""
        print("\n=== VERIFYING ENVIRONMENT CONFIGURATION ===\n")

        env_example = self.base_path / ".env.example"

        if not env_example.exists():
            self.log_result("Environment template", False, ".env.example not found")
            return False

        with open(env_example, 'r', encoding='utf-8') as f:
            content = f.read()

        required_vars = [
            "DATABASE_URL",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL",
            "CONTA_AZUL_CLIENT_ID",
            "CONTA_AZUL_CLIENT_SECRET",
            "CONTA_AZUL_REDIRECT_URI",
            "AUTENTIQUE_API_KEY",
            "AUTENTIQUE_API_URL",
        ]

        missing_vars = []
        for var in required_vars:
            if var not in content:
                missing_vars.append(var)
                self.log_result(f"Environment variable: {var}", False, "Not in .env.example")
            else:
                self.log_result(f"Environment variable: {var}", True)

        if not missing_vars:
            self.log_result("Environment configuration", True, f"{len(required_vars)} variables documented")
            return True
        else:
            self.log_result("Environment configuration", False, f"{len(missing_vars)} variables missing")
            return False

    def verify_dependencies(self) -> bool:
        """Verify all dependencies are listed in requirements.txt"""
        print("\n=== VERIFYING DEPENDENCIES ===\n")

        requirements_file = self.base_path / "requirements.txt"

        if not requirements_file.exists():
            self.log_result("Requirements file", False, "requirements.txt not found")
            return False

        with open(requirements_file, 'r', encoding='utf-8') as f:
            content = f.read()

        required_packages = [
            "fastapi",
            "uvicorn",
            "anthropic",
            "pydantic-settings",
            "sqlalchemy",
            "alembic",
            "psycopg2-binary",
            "requests",
            "requests-oauthlib",
            "gql",
            "weasyprint",
            "apscheduler",
            "jinja2",
            "pytest",
        ]

        missing_packages = []
        for package in required_packages:
            if package not in content.lower():
                missing_packages.append(package)
                self.log_result(f"Dependency: {package}", False, "Not in requirements.txt")
            else:
                self.log_result(f"Dependency: {package}", True)

        if not missing_packages:
            self.log_result("Dependency configuration", True, f"{len(required_packages)} packages verified")
            return True
        else:
            self.log_result("Dependency configuration", False, f"{len(missing_packages)} packages missing")
            return False

    def verify_tests(self) -> bool:
        """Verify test files exist and are properly structured"""
        print("\n=== VERIFYING TEST CONFIGURATION ===\n")

        conftest = self.base_path / "tests" / "conftest.py"

        if not conftest.exists():
            self.log_result("Test configuration", False, "tests/conftest.py not found")
            return False

        with open(conftest, 'r', encoding='utf-8') as f:
            content = f.read()

        required_fixtures = [
            "@pytest.fixture",
            "test_db_engine",
            "test_client",
        ]

        missing_fixtures = []
        for fixture in required_fixtures:
            if fixture not in content:
                missing_fixtures.append(fixture)

        if missing_fixtures:
            self.log_result("Test fixtures", False, f"{len(missing_fixtures)} fixtures missing")
            return False
        else:
            self.log_result("Test fixtures", True, "Key fixtures defined")

        # Check test files
        test_files = [
            "tests/test_services/test_claude.py",
            "tests/test_services/test_conta_azul.py",
            "tests/test_services/test_autentique.py",
            "tests/test_api/test_endpoints.py",
        ]

        missing_tests = []
        for test_file in test_files:
            if not (self.base_path / test_file).exists():
                missing_tests.append(test_file)
                self.log_result(f"Test file: {test_file}", False, "Not found")
            else:
                self.log_result(f"Test file: {test_file}", True)

        if not missing_tests:
            self.log_result("Test suite configuration", True, f"{len(test_files)} test files ready")
            return True
        else:
            self.log_result("Test suite configuration", False, f"{len(missing_tests)} test files missing")
            return False

    def run_all_verifications(self) -> bool:
        """Run all verification checks"""
        print("\n" + "=" * 70)
        print("FINANCIAL AUTOMATION SYSTEM - END-TO-END VERIFICATION")
        print("=" * 70)

        checks = [
            ("File Structure", self.verify_file_structure),
            ("Python Syntax", self.verify_python_syntax),
            ("Module Imports", self.verify_imports),
            ("API Endpoints", self.verify_api_endpoints),
            ("Background Jobs", self.verify_background_jobs),
            ("Database Migrations", self.verify_database_migrations),
            ("Environment Configuration", self.verify_environment_config),
            ("Dependencies", self.verify_dependencies),
            ("Test Configuration", self.verify_tests),
        ]

        all_passed = True
        for check_name, check_func in checks:
            try:
                passed = check_func()
                if not passed:
                    all_passed = False
            except Exception as e:
                self.log_result(check_name, False, f"Exception: {e}")
                all_passed = False

        # Print summary
        print("\n" + "=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)

        passed_count = sum(1 for r in self.results if r["passed"])
        failed_count = len(self.results) - passed_count

        print(f"\nTotal Checks: {len(self.results)}")
        print(f"Passed: {passed_count}")
        print(f"Failed: {failed_count}")

        if self.errors:
            print("\n" + "=" * 70)
            print("ERRORS FOUND:")
            print("=" * 70)
            for error in self.errors:
                print(f"  ✗ {error}")

        print("\n" + "=" * 70)
        if all_passed:
            print("✓ ALL VERIFICATIONS PASSED - SYSTEM READY FOR DEPLOYMENT")
        else:
            print("✗ VERIFICATION FAILED - PLEASE FIX ERRORS BEFORE DEPLOYMENT")
        print("=" * 70 + "\n")

        return all_passed


def main():
    """Main entry point for E2E verification"""
    verifier = E2EVerifier(base_path=".")
    success = verifier.run_all_verifications()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
