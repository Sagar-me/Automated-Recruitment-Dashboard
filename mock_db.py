import datetime
import random
from faker import Faker
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Enum
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# --- CONFIGURATION ---
DB_URL = "mysql+mysqlconnector://root:Rekie%40123@localhost:3306/email_stats"
# ---------------------

# Initialize Faker for data generation
fake = Faker()

# SQLAlchemy setup
try:
    engine = create_engine(DB_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
except Exception as e:
    print(f"Error connecting to database: {e}")
    print("Please ensure your MySQL server is running and the DB_URL is correct.")
    exit()

# Define the Email model (table)
class Email(Base):
    __tablename__ = "emails"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.now(datetime.timezone.utc)) 
    direction = Column(Enum('sent', 'received'), nullable=False)
    is_reply = Column(Boolean, default=False)
    sender_email = Column(String(255))
    recipient_email = Column(String(255))

    # --- NEW COLUMNS ADDED ---
    company_name = Column(String(255))
    company_size = Column(String(50)) 
    company_industry = Column(String(100)) 
    contact_title = Column(String(100)) 
    reply_sentiment = Column(Enum('positive', 'neutral', 'negative', 'N/A'), default='N/A')
    
    # --- COLUMNS ADDED FOR DASHBOARD ANALYSIS ---
    ai_agent = Column(String(100)) # e.g., 'Agent Alpha', 'Manual'
    city = Column(String(100))     # e.g., 'New York', 'London'
    reply_time_delta_seconds = Column(Integer, nullable=True) # Stored in seconds for analysis
    # -------------------------

# Function to generate mock data
def generate_mock_data(session, num_entries=10000):
    print(f"Generating {num_entries} mock email entries...")
    
    my_email = "your_company@example.com"
    entries = []

    # Lists for mock data generation
    INDUSTRIES = ['Tech', 'Finance', 'Healthcare', 'Manufacturing', 'Retail', 'Education', 'Non-Profit']
    COMPANY_SIZES = ['1-50', '51-200', '201-1000', '1000+']
    CONTACT_TITLES = ['CEO', 'CTO', 'Founder', 'VP of Sales', 'HR Manager', 'Software Engineer', 'Marketing Director']
    REPLY_SENTIMENTS = ['positive', 'neutral', 'negative']
    AGENTS = ['Agent Alpha', 'Agent Beta', 'Agent Gamma']
    CITIES = ['New York', 'San Francisco', 'London', 'Berlin', 'Tokyo', 'Singapore', 'Mumbai', 'Sydney', 'Beijing', 'Moscow']
    
    # -------------------------------------------------------------
    # 1. Generate ALL Sent Emails first (The "Outreach")
    # Store key data to link replies back to the original sent agent
    sent_emails_map = {} 
    
    for i in range(int(num_entries * 0.5)): # Generate 50% of the total as initial sent outreach
        timestamp = fake.date_time_between(start_date="-90d", end_date="-1d") # Sent before replies
        recipient_contact = fake.email()
        
        # Determine agent and city for the sent email
        assigned_agent = random.choice(AGENTS)
        assigned_city = random.choice(CITIES)
        
        sent_entry = Email(
            timestamp=timestamp,
            direction='sent',
            is_reply=False,
            sender_email=my_email,
            recipient_email=recipient_contact,
            company_name=fake.company(),
            company_size=random.choice(COMPANY_SIZES),
            company_industry=random.choice(INDUSTRIES),
            contact_title=random.choice(CONTACT_TITLES),
            reply_sentiment='N/A',
            ai_agent=assigned_agent,
            city=assigned_city,
            reply_time_delta_seconds=None
        )
        entries.append(sent_entry)

        # Map the recipient to the agent and city
        sent_emails_map[recipient_contact] = {
            'agent': assigned_agent,
            'city': assigned_city,
            'sent_timestamp': timestamp
        }

    # -------------------------------------------------------------
    # 2. Generate Replies based on the Sent Emails
    
    # For simplicity, we will assume a certain percentage of sent emails receive replies
    # and a certain percentage of received emails are completely new/unrelated.
    
    # Emails that receive replies
    replied_contacts = random.sample(list(sent_emails_map.keys()), k=int(len(sent_emails_map) * 0.4))
    
    for contact in replied_contacts:
        original_sent_data = sent_emails_map[contact]
        
        # Calculate reply details
        reply_sentiment = random.choice(REPLY_SENTIMENTS)
        reply_time_delta_seconds = random.randint(3600, 864000) # 1 hour to 10 days
        reply_timestamp = original_sent_data['sent_timestamp'] + datetime.timedelta(seconds=reply_time_delta_seconds)
        
        # Create the RECEIVED REPLY entry
        received_entry = Email(
            timestamp=reply_timestamp,
            direction='received',
            is_reply=True,
            sender_email=contact,
            recipient_email=my_email,
            company_name=fake.company(),
            company_size=random.choice(COMPANY_SIZES),
            company_industry=random.choice(INDUSTRIES),
            contact_title=random.choice(CONTACT_TITLES),
            reply_sentiment=reply_sentiment,
            
            # CRITICAL: Inherit the AI Agent from the original sent email
            ai_agent=original_sent_data['agent'], 
            city=original_sent_data['city'],
            reply_time_delta_seconds=reply_time_delta_seconds
        )
        entries.append(received_entry)

    # 3. Add some random incoming emails that are not replies (not necessary for the chart, but good data)
    for _ in range(int(num_entries * 0.1)): # 10% random incoming
        received_entry = Email(
            timestamp=fake.date_time_between(start_date="-90d", end_date="now"),
            direction='received',
            is_reply=False,
            sender_email=fake.email(),
            recipient_email=my_email,
            # Assign 'Manual' or 'N/A' for unrelated incoming emails
            ai_agent=random.choice(['Manual', 'N/A']), 
            # ... (other fields as filler) ...
            reply_sentiment='N/A',
            company_name=fake.company(),
            company_size=random.choice(COMPANY_SIZES),
            company_industry=random.choice(INDUSTRIES),
            contact_title=random.choice(CONTACT_TITLES),
            city=random.choice(CITIES),
            reply_time_delta_seconds=None
        )
        entries.append(received_entry)

    session.bulk_save_objects(entries)
    session.commit()
    print(f"Successfully added {len(entries)} entries to the database.")


# Main function to run the script
def main():
    session = SessionLocal()
    try:
        print("Dropping and recreating 'emails' table...")
        # Drop the table if it exists (for easy re-running)
        Base.metadata.drop_all(bind=engine, tables=[Email.__table__])
        # Create the table
        Base.metadata.create_all(bind=engine)
        print("Table created.")
        
        # Populate with data
        generate_mock_data(session)
        
    except Exception as e:
        print(f"An error occurred: {e}")
        session.rollback()
    finally:
        session.close()
        print("Database connection closed.")

if __name__ == "__main__":
    main()