import pandas as pd
import matplotlib
matplotlib.use('Agg')  # render to files only; the default GUI backend crashes in Flask's worker threads
import matplotlib.pyplot as plt
import seaborn as sns
from flask import Flask, render_template
import os

app = Flask(__name__)

# Ensure static folder exists
os.makedirs("static", exist_ok=True)

# Load and preprocess data
def load_and_preprocess_data():
    file_path = "Daily Household Transactions.csv"
    df = pd.read_csv(file_path)
    
    # Convert Date column to datetime
    # Dates are day-first, some with a time and some without ("20/09/2018 12:04:08", "19/09/2018")
    df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Date'])

    # Extract additional date-based features
    df['YearMonth'] = df['Date'].dt.to_period('M')
    df['Year'] = df['Date'].dt.year
    df['Month'] = df['Date'].dt.month
    df['Quarter'] = df['Date'].dt.to_period('Q')

    return df

# Generate visualizations
def generate_visualizations(df):
    # Monthly Spending Trends
    monthly_spending = df[df['Income/Expense'] == 'Expense'].groupby('YearMonth')['Amount'].sum()
    plt.figure(figsize=(10, 5))
    plt.plot(monthly_spending.index.astype(str), monthly_spending.values, marker='o', linestyle='-', color='b')
    plt.title('Monthly Spending Trends')
    plt.xlabel('Month')
    plt.ylabel('Total Spending (INR)')
    plt.xticks(rotation=45)
    plt.grid(alpha=0.5)
    plt.tight_layout()
    plt.savefig('static/monthly_spending_trends.png')
    plt.close()

    # Category-Wise Breakdown
    category_spending = df[df['Income/Expense'] == 'Expense'].groupby('Category')['Amount'].sum().sort_values(ascending=False)
    plt.figure(figsize=(9, 6))
    sns.barplot(x=category_spending.values, y=category_spending.index, palette='viridis', orient='h')
    plt.title('Category-Wise Breakdown of Expenses')
    plt.xlabel('Total Spending (INR)')
    plt.ylabel('Category')
    plt.tight_layout()
    plt.savefig('static/category_breakdown.png')
    plt.close()

    # Payment Mode Analysis
    payment_modes = df.groupby('Mode')['Amount'].sum()
    plt.figure(figsize=(9, 5))
    sns.barplot(x=payment_modes.values, y=payment_modes.index, palette='coolwarm', orient='h')
    plt.title('Payment Mode Distribution')
    plt.xlabel('Total Amount (INR)')
    plt.ylabel('Mode')
    plt.tight_layout()
    plt.savefig('static/payment_mode_analysis.png')
    plt.close()

    # Spending Heatmap
    heatmap_data = df[df['Income/Expense'] == 'Expense'].pivot_table(
        index='Year', columns='Month', values='Amount', aggfunc='sum', fill_value=0)
    plt.figure(figsize=(10, 6))
    sns.heatmap(heatmap_data, annot=True, fmt=".0f", cmap="YlGnBu", linewidths=0.5)
    plt.title('Heatmap of Monthly Spending by Year')
    plt.xlabel('Month')
    plt.ylabel('Year')
    plt.tight_layout()
    plt.savefig('static/spending_heatmap.png')
    plt.close()

    # Category-Wise Spending (Pie Chart) - Without `adjust_text`
    category_pie = df[df['Income/Expense'] == 'Expense'].groupby('Category')['Amount'].sum()
    plt.figure(figsize=(8, 8))
    colors = sns.color_palette('pastel')
    wedges, texts, autotexts = plt.pie(
        category_pie, labels=category_pie.index, autopct=lambda p: '{:.1f}%'.format(p) if p > 5 else '',
        startangle=140, colors=colors, pctdistance=0.85, wedgeprops={'edgecolor': 'black'})
    
    # Improve text visibility
    for text in texts + autotexts:
        text.set_bbox(dict(facecolor='white', alpha=0.6, edgecolor='none'))
    
    plt.title('Category-Wise Spending Distribution')
    plt.tight_layout()
    plt.savefig('static/category_pie_chart.png')
    plt.close()

    # Yearly Spending Analysis
    yearly_expense = df[df['Income/Expense'] == 'Expense'].groupby('Year')['Amount'].sum().reset_index()
    plt.figure(figsize=(8, 5))
    sns.barplot(data=yearly_expense, x='Year', y='Amount', palette='pastel')
    plt.xlabel('Year')
    plt.ylabel('Total Spending')
    plt.title('Yearly Spending Analysis')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig('static/yearly_spending.png')
    plt.close()

    # Quarterly Spending Analysis
    quarterly_expense = df[df['Income/Expense'] == 'Expense'].groupby('Quarter')['Amount'].sum().reset_index()
    plt.figure(figsize=(8, 5))
    sns.barplot(data=quarterly_expense, x='Quarter', y='Amount', palette='pastel')
    plt.xlabel('Quarter')
    plt.ylabel('Total Spending')
    plt.title('Quarterly Spending Analysis')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig('static/quarterly_spending.png')
    plt.close()
    
    # Category-Wise Spending Over Time
    category_monthly = df[df['Income/Expense'] == 'Expense'].groupby(['YearMonth', 'Category'])['Amount'].sum().unstack().fillna(0)
    category_monthly.index = category_monthly.index.astype(str)
    plt.figure(figsize=(12, 6))
    plt.stackplot(category_monthly.index, category_monthly.T, labels=category_monthly.columns, alpha=0.7)
    plt.legend(loc='upper left')
    plt.xlabel('Month')
    plt.ylabel('Total Spending')
    plt.title('Category-Wise Spending Over Time')
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    plt.savefig('static/category_over_time.png')
    plt.close()

# Flask Route
@app.route('/')
def index():
    df = load_and_preprocess_data()
    generate_visualizations(df)
    visualizations = {
        'monthly_trends': '/static/monthly_spending_trends.png',
        'category_breakdown': '/static/category_breakdown.png',
        'payment_modes': '/static/payment_mode_analysis.png',
        'spending_heatmap': '/static/spending_heatmap.png',
        'category_pie': '/static/category_pie_chart.png',
        'yearly_spending': '/static/yearly_spending.png',
        'quarterly_spending': '/static/quarterly_spending.png',
        'category_over_time': '/static/category_over_time.png'
    }
    return render_template('index.html', visualizations=visualizations)

if __name__ == '__main__':
    app.run(debug=True)

