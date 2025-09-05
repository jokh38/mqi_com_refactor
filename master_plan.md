### 🛠️ AI Coding Assistant Prompt: Code Refactoring Plan

**Objective:**  
Refactor the existing program located at `/mqi_communicator` by creating a new codebase under `/mqi_com_refactor`. The goal is to generate Python script skeletons that preserve the core functionality of the original system while improving structure and maintainability.

---

### 📁 Project Structure

- **Original Program Path:** `/mqi_communicator`  
- **New Program Path:** `/mqi_com_refactor`

---

### 🧭 Instructions

1. **Reference Document:**  
   Use `/mqi_communicator/refactor_E.md` as the primary guideline for refactoring.

2. **Template Usage:**  
   Use `/mqi_com_refactor/template_database_handler.py` as a template to define:
   - The file structure of the new codebase  
   - Skeletons of all required Python scripts within that structure

3. **Skeleton Requirements:**  
   - Each script must include all necessary dependencies  
   - Variables and type hints must be clearly defined  
   - Follow the style and completeness of the provided template

4. **Source Material:**  
   - Do **not** read the original Python files directly from `/mqi_communicator`  
   - Instead, refer to the **JSON-translated versions** of those files as context for generating new code

5. **Functional Fidelity:**  
   - The new skeletons must fully preserve the core functionality of the original system  
   - Refactoring should emphasize clarity, modularity, and future extensibility

---

### ⚠️ Important Notes for AI Coding Assistant

- This prompt is designed for use in **stateless AI coding sessions**.  
  The assistant has **no memory of previous sessions** and **no global understanding** of the entire codebase.

- The full development plan is provided in `refactor_E.md`, while each Python script will be developed individually using consistent instructions.

- The assistant will be given contextual references (e.g., JSON-translated original code) during each session to guide implementation.

- The new code should **highlight improvements** over the original while **preserving its functionality**.

- When filling in details not explicitly defined in the documentation, the assistant must:
  - Infer and implement only what is necessary to fulfill the plan  
  - **Avoid adding or changing anything** beyond the scope of the instructions—even if a better method exists


