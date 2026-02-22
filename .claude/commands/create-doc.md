User instruction: $ARGUMENTS

## Your Task
1. Analyze the instruction above and identify:
   - Document type (pptx / docx)
   - Purpose and target audience
   - Required sections / slide count
   - Data, charts, and table requirements
2. Create feature_list.json with each element in this format:
   ```json
   {"id": 1, "description": "Create title slide", "passes": false}
   ```
3. Implement items from feature_list.json one by one
4. After completing each item, run `git add -A && git commit` and update claude-progress.txt
5. After all items are done, run final verification
6. Output the final file to the output/ directory

## Important Rules
- The description field in feature_list.json must NOT be edited (only the passes field may change)
- Work on one item at a time; move to the next only after completion
- Template files must NEVER be overwritten
- Output filenames must include a datetime stamp
- Verify the generated file can be opened/parsed before marking complete
