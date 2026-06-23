import os

def record_files():
    # The files you want to target
    target_files = ['graph.py', 'agents.py', 'state.py', 'main.py']
    output_filename = 'project_summary.txt'
    
    # Get the directory where this script is running
    current_dir = os.getcwd()
    
    with open(output_filename, 'w', encoding='utf-8') as outfile:
        outfile.write(f"=== PROJECT CODE DUMP ===\n")
        outfile.write(f"Generated on: {os.path.basename(current_dir)}\n")
        outfile.write("=" * 25 + "\n\n")
        
        found_any = False
        
        for filename in target_files:
            file_path = os.path.join(current_dir, filename)
            
            if os.path.exists(file_path):
                found_any = True
                outfile.write(f"// {'=' * 10} START OF FILE: {filename} {'=' * 10}\n")
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    outfile.write(f"[Error reading file: {e}]\n")
                
                outfile.write(f"\n// {'=' * 10} END OF FILE: {filename} {'=' * 10}\n\n\n")
            else:
                outfile.write(f"// [Notice] {filename} was not found in this directory.\n\n")
                print(f"⚠️ {filename} not found.")

    if found_any:
        print(f"✅ Success! Contents recorded into '{output_filename}'.")
    else:
        print(f"❌ None of the targeted files were found in {current_dir}.")

if __name__ == "__main__":
    record_files()
