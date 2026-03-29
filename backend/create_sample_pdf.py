"""
Sample PDF generator for testing
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
import os


def create_sample_pdf(output_path: str = "sample_document.pdf"):
    """Create a sample PDF with clauses and tables for testing"""
    
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
    )
    story.append(Paragraph("Technical Specification Document", title_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Section 1
    story.append(Paragraph("1 Scope", styles['Heading1']))
    story.append(Paragraph(
        "This document specifies the requirements for the system implementation.",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.2*inch))
    
    # Section 1.1
    story.append(Paragraph("1.1 General Requirements", styles['Heading2']))
    story.append(Paragraph(
        "The system shall comply with the following requirements:",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.1*inch))
    
    # Sub-items
    story.append(Paragraph("(a) Requirement A: System must be scalable", styles['Normal']))
    story.append(Paragraph("(b) Requirement B: System must be secure", styles['Normal']))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;(i) SSL/TLS encryption required", styles['Normal']))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;(ii) Authentication mechanisms must be implemented", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    
    # Note
    story.append(Paragraph("<b>NOTE:</b> Security requirements are mandatory.", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Section 2
    story.append(Paragraph("2 Performance Specifications", styles['Heading1']))
    story.append(Paragraph(
        "The following performance metrics shall be maintained:",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.2*inch))
    
    # Table
    data = [
        ['Metric', 'Target Value', 'Unit'],
        ['Response Time', '< 100', 'ms'],
        ['Throughput', '> 1000', 'req/s'],
        ['Uptime', '99.9', '%'],
    ]
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    story.append(Paragraph("<b>Table 2.1:</b> Performance Requirements", styles['Normal']))
    story.append(Spacer(1, 0.1*inch))
    story.append(t)
    story.append(Spacer(1, 0.3*inch))
    
    # Section 2.1
    story.append(Paragraph("2.1 Load Testing", styles['Heading2']))
    story.append(Paragraph(
        "Load testing shall be performed under peak conditions.",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "<b>Exception:</b> Testing may be deferred if production environment is unavailable.",
        styles['Normal']
    ))
    
    # Build PDF
    doc.build(story)
    print(f"Sample PDF created: {output_path}")


if __name__ == "__main__":
    create_sample_pdf()
