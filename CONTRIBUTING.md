# Contributing to ODW.ai Desk

Thank you for your interest in contributing to ODW.ai Desk! This document provides guidelines and information for contributors.

## Code of Conduct

This project adheres to a code of conduct that promotes a welcoming and inclusive environment. Please be respectful and constructive in all interactions.

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Use the bug report template
3. Include:
   - Clear description of the issue
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)
   - Relevant logs or error messages

### Suggesting Features

1. Check existing issues and discussions
2. Use the feature request template
3. Describe the problem you're solving
4. Explain your proposed solution
5. Consider alternatives and trade-offs

### Submitting Changes

1. **Fork the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/odw-desk.git
   cd odw-desk
   ```

2. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

3. **Make your changes**
   - Follow the existing code style
   - Add tests for new functionality
   - Update documentation as needed
   - Ensure all tests pass

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "Description of changes"
   ```
   
   Use conventional commit format:
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation changes
   - `style:` Code style changes (formatting, etc.)
   - `refactor:` Code refactoring
   - `test:` Adding or updating tests
   - `chore:` Maintenance tasks

5. **Push to your fork**
   ```bash
   git push origin your-branch-name
   ```

6. **Open a Pull Request**
   - Use the PR template
   - Link related issues
   - Describe your changes
   - Request review from maintainers

## Development Setup

### Prerequisites

- Python 3.14+
- PostgreSQL 16+
- Redis 7+
- Git

### Local Development

1. **Clone and setup**
   ```bash
   git clone https://github.com/OnDemandWorld/odw-desk.git
   cd odw-desk
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Initialize database**
   ```bash
   alembic upgrade head
   ```

4. **Run tests**
   ```bash
   pytest tests/ -v
   ```

5. **Start development server**
   ```bash
   uvicorn desk.main:app --reload
   ```

## Code Style

### Python

- **Formatter**: Black (line length 100)
- **Linter**: Ruff
- **Type checker**: MyPy
- **Import sorting**: isort

Run before committing:
```bash
ruff check src/desk/ --fix
black src/desk/
isort src/desk/
mypy src/desk/
```

### Guidelines

- Use type hints for all function signatures
- Write docstrings for all public functions/classes
- Keep functions focused and small
- Use async/await for I/O operations
- Follow existing naming conventions
- Add comments for complex logic

## Testing

### Types of Tests

1. **Unit Tests**: Test individual functions/classes
2. **Integration Tests**: Test component interactions
3. **E2E Tests**: Test complete workflows

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/integration/test_message_pipeline.py -v

# With coverage
pytest --cov=desk --cov-report=html

# E2E tests (requires running app)
pytest tests/e2e/ -v
```

### Writing Tests

- Use pytest with pytest-asyncio for async tests
- Mock external services (LLM, Vault, etc.)
- Test both success and error paths
- Include edge cases
- Keep tests independent and idempotent

Example:
```python
import pytest
from desk.ai.pii_shield import PIIShield

@pytest.mark.asyncio
async def test_pii_detection():
    shield = PIIShield()
    result = await shield.analyze("My SSN is 123-45-6789")
    assert result.pii_detected is True
    assert "US_SSN" in result.pii_types
```

## Documentation

### Types of Documentation

1. **Code Documentation**: Docstrings, type hints, comments
2. **API Documentation**: Auto-generated from FastAPI
3. **User Documentation**: README, guides, tutorials
4. **Developer Documentation**: Architecture, design decisions

### Updating Documentation

- Update README.md for user-facing changes
- Update DEVELOPMENT.md for technical changes
- Add inline documentation for complex logic
- Keep API documentation in sync with code

## Architecture Guidelines

### Adding a New Channel Adapter

1. Create adapter class in `src/desk/channels/`
2. Inherit from `ChannelAdapter` base class
3. Implement required methods:
   - `connect()`
   - `disconnect()`
   - `receive()`
   - `send()`
   - `health_check()`
4. Add to channel manager registration
5. Write tests
6. Update documentation

### Adding a New AI Component

1. Create component in `src/desk/ai/`
2. Follow existing component patterns
3. Integrate with AI Engine orchestrator
4. Add configuration to settings
5. Write tests
6. Update documentation

## Pull Request Process

### Before Submitting

- [ ] Code follows style guidelines
- [ ] All tests pass
- [ ] New tests added for new functionality
- [ ] Documentation updated
- [ ] No linting errors
- [ ] Type checking passes
- [ ] Commit messages follow convention

### Review Process

1. **Automated Checks**: CI/CD pipeline runs automatically
2. **Code Review**: At least one maintainer review required
3. **Discussion**: Address feedback and make changes
4. **Approval**: Maintainer approves the PR
5. **Merge**: Maintainer merges the PR

### After Merge

- Delete your feature branch
- Sync your fork with upstream
- Celebrate your contribution! 🎉

## Getting Help

- **Documentation**: Check README.md and DEVELOPMENT.md
- **Issues**: Search existing issues or create new one
- **Discussions**: Use GitHub Discussions for questions
- **Discord**: Join our community (link in README)

## Recognition

Contributors are recognized in:
- README.md contributors section
- Release notes
- Project documentation

Thank you for contributing to ODW.ai Desk! 🙏
