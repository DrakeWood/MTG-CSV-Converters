import pandas as pd
import re
import sys
from tkinter import Tk, filedialog, Button, Label, Entry, messagebox
import os

def process_csv(input_file, output_file='cardtrader_to_manabox_output.csv'):
    try:
        # Read the CSV file
        df = pd.read_csv(input_file)
        
        # Rename columns
        df.rename(columns={
            'Item Name': 'card name',
            'Quantity': 'quantity',
            'Set Code': 'set code',
            'Foil/Reverse': 'foil',
            'Collector Number': 'card number',
            'Price in USD Cents': 'purchase price',
            'Condition': 'condition',
            'Language': 'language'
        }, inplace=True)
        
        # Remove unwanted columns if they exist
        columns_to_drop = ['game', 'set name', 'set released at', 'set release', 'signed', 'first edition', 'playset', 'altered']
        columns_to_drop = [col.lower() for col in columns_to_drop]
        df.columns = [col.lower() for col in df.columns]
        df.drop(columns=[col for col in columns_to_drop if col in df.columns], inplace=True)
        
        # Add 'purchase currency' column with 'usd' as value for all rows
        df['purchase currency'] = 'usd'
        
        # Clean up 'card name' column
        df['card name'] = df['card name'].apply(lambda x: re.sub(r'\s*\(.*?\)\s*', '', x).strip())
        
        # Convert 'purchase price' from cents to dollars and cents
        df['purchase price'] = df['purchase price'].apply(lambda x: x / 100)
        
        # Format 'card number' column values as strings with leading zeros
        df['card number'] = df['card number'].apply(lambda x: str(x).zfill(3))
        
        # Fix promos. Append 'p' to 'card number' if 'set code' has 4 letters and starts with 'P'
        df['card number'] = df.apply(lambda row: str(row['card number']) + 'p' if len(str(row['set code'])) == 4 and str(row['set code']).startswith('P') else row['card number'], axis=1)
        
        # Fix prereleases. Append 's' to 'card number' if 'set code' has 4 letters and starts with 'S'
        df['card number'] = df.apply(lambda row: str(row['card number']) + 's' if len(str(row['set code'])) == 4 and str(row['set code']).startswith('S') else row['card number'], axis=1)
        
        # Modify 'set code' column, remove first character if there are 4
        df['set code'] = df['set code'].apply(lambda x: str(x)[1:] if len(str(x)) == 4 else str(x))
        
        # Miscellaneous set code corrections
        # Replace 'IDF' with 'DBL' for Innistrad: Double Feature
        df['set code'] = df['set code'].replace({'IDF': 'DBL'})
        
        # Replace 'FND' with 'FDN' for Foundations Collectors
        df['set code'] = df['set code'].replace({'FND': 'FDN'})
        
        # Replace 'TCH' with 'LTC' for Tales of Middle-earth Holiday Release Commander
        df['set code'] = df['set code'].replace({'TCH': 'LTC'})
        
        # Replace 'TRH' with 'LTC' for Tales of Middle-earth Holiday Release
        df['set code'] = df['set code'].replace({'TRH': 'LTR'})
        
        # Replace 'DCM' with 'DMC' for Dominaria United Commander
        df['set code'] = df['set code'].replace({'DCM': 'DMC'})
        
        # Replace 'PLST2' with 'PLST' for MB2
        df['set code'] = df['set code'].replace({'PLIST2': 'PLST'})
        
        # Replace 'SLD-20WTW' with 'SLD' for 20 Ways to Win Deck
        df['set code'] = df['set code'].replace({'SLD-20WTW': 'SLD'})
        
        # change set code from CSNCC to NCC for New Capenna Commander
        df['set code'] = df['set code'].replace({'CSNCC': 'NCC'})
        
        # change set from EOC to NEC for Neon Dynasty Commander
        df['set code'] = df['set code'].replace({'EOC': 'NEC'})
        
        #change set from VOWCOM to VOC for Crimson Vow Commander
        df['set code'] = df['set code'].replace({'VOWCOM': 'VOC'})
        
        #change set from MB1 to PLST for Mystery Booster 1
        df['set code'] = df['set code'].replace({'MB1': 'PLST'})
        
        # change PRE to 2XM for Double Masters 2022 Prerelease Wrath of God
        df['set code'] = df['set code'].replace({'PRE': '2XM'})
        
        # BAB buy a box cant be fixed.
        # Phyrexian Dragon Engine // Mishra, Lost to Phyrexia

        # Save the updated DataFrame to a new CSV file
        df.to_csv(output_file, index=False)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred during conversion: {e}")
        return False

def select_input_file():
    global input_file
    input_file = filedialog.askopenfilename(title="Select input CSV file", filetypes=[("CSV files", "*.csv")])
    if input_file:
        input_label.config(text=f"Input File: {input_file}")

def run_conversion():
    global output_file
    if not input_file:
        messagebox.showerror("Error", "Please select an input file.")
        return
    output_file = os.path.join(os.path.dirname(__file__), output_entry.get())
    if not output_file:
        messagebox.showerror("Error", "Please specify an output file.")
        return
    if process_csv(input_file, output_file):
        messagebox.showinfo("Done", "Conversion completed successfully!")
        os.startfile(os.path.dirname(output_file))

if __name__ == '__main__':
    input_file = None

    root = Tk()
    root.title("Cardtrader to Manabox Converter")

    input_button = Button(root, text="Select Input File", command=select_input_file)
    input_button.pack(pady=10)

    input_label = Label(root, text="Input File: None")
    input_label.pack(pady=5)

    output_label = Label(root, text="Output File:")
    output_label.pack(pady=5)

    output_entry = Entry(root, width=50)
    output_entry.insert(0, 'cardtrader_to_manabox_output.csv')
    output_entry.pack(pady=5)

    convert_button = Button(root, text="Run Conversion", command=run_conversion)
    convert_button.pack(pady=20)

    root.mainloop()
