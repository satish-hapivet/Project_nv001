"""Hospital knowledge base containing information about doctors, departments, services, and emergencies."""

HOSPITAL_DATA = {
    'doctors': {
        'cardiology': [
            {'name': 'Dr. Sarah Johnson', 'specialization': 'Cardiology', 'availability': 'Mon-Fri 9AM-5PM'},
            {'name': 'Dr. Michael Chen', 'specialization': 'Interventional Cardiology', 'availability': 'Tue-Sat 10AM-4PM'}
        ],
        'neurology': [
            {'name': 'Dr. Emily Williams', 'specialization': 'Neurology', 'availability': 'Mon-Wed-Fri 8AM-3PM'},
            {'name': 'Dr. James Anderson', 'specialization': 'Neurosurgery', 'availability': 'Mon-Fri 9AM-6PM'}
        ],
        'pediatrics': [
            {'name': 'Dr. Lisa Martinez', 'specialization': 'Pediatrics', 'availability': 'Mon-Fri 8AM-4PM'},
            {'name': 'Dr. Robert Taylor', 'specialization': 'Pediatric Surgery', 'availability': 'Tue-Thu 10AM-5PM'}
        ],
        'orthopedics': [
            {'name': 'Dr. David Brown', 'specialization': 'Orthopedics', 'availability': 'Mon-Sat 9AM-5PM'},
            {'name': 'Dr. Jennifer Lee', 'specialization': 'Sports Medicine', 'availability': 'Mon-Fri 8AM-3PM'}
        ]
    },
    
    'departments': {
        'emergency': {
            'name': 'Emergency Department',
            'location': 'Ground Floor, Wing A',
            'hours': '24/7',
            'contact': '911 or Extension 100'
        },
        'cardiology': {
            'name': 'Cardiology Department',
            'location': '3rd Floor, Wing B',
            'hours': 'Mon-Fri 8AM-6PM, Sat 9AM-1PM',
            'contact': 'Extension 301'
        },
        'neurology': {
            'name': 'Neurology Department',
            'location': '4th Floor, Wing C',
            'hours': 'Mon-Fri 8AM-5PM',
            'contact': 'Extension 401'
        },
        'pediatrics': {
            'name': 'Pediatrics Department',
            'location': '2nd Floor, Wing A',
            'hours': 'Mon-Fri 8AM-6PM, Sat 9AM-2PM',
            'contact': 'Extension 201'
        },
        'orthopedics': {
            'name': 'Orthopedics Department',
            'location': '3rd Floor, Wing C',
            'hours': 'Mon-Sat 8AM-5PM',
            'contact': 'Extension 302'
        },
        'radiology': {
            'name': 'Radiology Department',
            'location': 'Ground Floor, Wing B',
            'hours': 'Mon-Fri 7AM-7PM, Sat-Sun 8AM-4PM',
            'contact': 'Extension 110'
        }
    },
    
    'services': {
        'laboratory': {
            'name': 'Laboratory Services',
            'description': 'Blood tests, urine analysis, pathology',
            'location': 'Ground Floor, Wing C',
            'hours': 'Mon-Fri 7AM-7PM, Sat 8AM-2PM'
        },
        'pharmacy': {
            'name': 'Hospital Pharmacy',
            'description': 'Prescription medications and medical supplies',
            'location': 'Ground Floor, Main Entrance',
            'hours': 'Mon-Sat 8AM-8PM, Sun 9AM-5PM'
        },
        'imaging': {
            'name': 'Medical Imaging',
            'description': 'X-ray, CT scan, MRI, Ultrasound',
            'location': 'Ground Floor, Wing B',
            'hours': 'Mon-Fri 7AM-7PM, Sat-Sun 8AM-4PM'
        },
        'cafeteria': {
            'name': 'Hospital Cafeteria',
            'description': 'Food and beverages for patients and visitors',
            'location': '1st Floor, Central Area',
            'hours': 'Daily 6AM-9PM'
        }
    },
    
    'emergency_info': {
        'general': 'For any medical emergency, please call 911 or come to the Emergency Department on Ground Floor, Wing A. We are open 24/7.',
        'chest_pain': 'If experiencing chest pain, call 911 immediately or go to Emergency Department. Do not drive yourself.',
        'stroke': 'For stroke symptoms (facial drooping, arm weakness, speech difficulty), call 911 immediately. Time is critical.',
        'injury': 'For serious injuries, go to Emergency Department immediately. For minor injuries, you can visit the Urgent Care center.',
        'ambulance': 'To request an ambulance, call 911. For non-emergency medical transport, call Extension 150.'
    }
}

def get_doctors_info(specialization=None):
    """Get information about doctors."""
    if specialization:
        spec_lower = specialization.lower()
        for dept, doctors in HOSPITAL_DATA['doctors'].items():
            if spec_lower in dept or any(spec_lower in doc['specialization'].lower() for doc in doctors):
                return doctors
        return None
    else:
        # Return all doctors
        all_doctors = []
        for doctors_list in HOSPITAL_DATA['doctors'].values():
            all_doctors.extend(doctors_list)
        return all_doctors

def get_department_info(department_name):
    """Get information about a specific department."""
    dept_lower = department_name.lower()
    for dept_key, dept_data in HOSPITAL_DATA['departments'].items():
        if dept_lower in dept_key or dept_lower in dept_data['name'].lower():
            return dept_data
    return None

def get_service_info(service_name):
    """Get information about a specific service."""
    service_lower = service_name.lower()
    for service_key, service_data in HOSPITAL_DATA['services'].items():
        if service_lower in service_key or service_lower in service_data['name'].lower():
            return service_data
    return None

def get_emergency_info(emergency_type=None):
    """Get emergency information."""
    if emergency_type:
        emerg_lower = emergency_type.lower()
        for key, info in HOSPITAL_DATA['emergency_info'].items():
            if emerg_lower in key:
                return info
        return HOSPITAL_DATA['emergency_info']['general']
    return HOSPITAL_DATA['emergency_info']['general']
