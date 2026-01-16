## Auth Migration Plan

### TODO(auth): Убрать default role после внедрения auth middleware

**Файлы для изменения:**
- `app/api/deps.py` (строка 35-50)
  - Убрать `"system"` default
  - Заменить на `...` (обязательный параметр)
  - Извлекать role из JWT/session

**Зависит от:**
- [ ] Внедрение auth middleware
- [ ] JWT token validation
- [ ] User role в session/token

**Риски:**
- Ломает текущие Postman тесты (нужно обновить)
- Требует auth в каждом запросе

---
### TODO(qc): move QC actions to separate router / FSM  
```
if payload.action.startswith("qc_"):
```
