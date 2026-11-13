from django.contrib import admin
from .models import Contact, SocialLedger, LedgerRepayment

# Register your models here.



admin.site.register(Contact)
admin.site.register(SocialLedger)
admin.site.register(LedgerRepayment)